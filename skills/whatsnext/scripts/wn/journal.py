"""The facts layer (ADR-0005, "facts" row): one journal line per Stop, PreCompact and SessionEnd.

`record` appends a line to `<paths.progress>/journal/<item>.md` (UTC time, event, short commit,
branch, dirty file count, files changed since the last line's commit), keeps per-session state in
`.whatsnext/sessions/<session_id>.json`, and refreshes the progress file header. No model call and
no transcript reading. It does nothing outside git or without an active task.

A journal line looks like (one line, at most MAX_LINE characters):
    - 2026-11-04T21:58Z stop 5367d1d design/x dirty=2 set=1a2b3c files: a.py, b.py
(`set=` is a short hash of the dirty file names, left out when none are dirty; P-1)
"""

import hashlib
import json
import os
import re
import stat
import time

from . import status as gwstatus

MAX_LINE = 200
LINE_RE = re.compile(r"^- \S+ \S+ (?P<commit>[0-9a-fA-F]{4,40}|%s) \S+ dirty=\d+" % gwstatus.NONE)
STATE_RE = re.compile(r"^- \S+ \S+ \S+ \S+ dirty=(?P<count>\d+)(?: set=(?P<set>[0-9a-f]{6}))?")
SESSIONS_DIR = os.path.join(".whatsnext", "sessions")
SESSION_ID_MAX = 100


SESSION_KEEP_DAYS = 14  # a session's state files go once none of them has changed for this long (ADR-0018)
# Only the files the hooks write per session: `<id>.json`, `<id>.handoff.json`, `<id>.summary.md.bak` and so on.
# `health-*.json` (doctor's evidence) and any other name are never pruned.
SESSION_FILE_RE = re.compile(r"^(?P<id>[A-Za-z0-9_-]+)"
                             r"(?:\.(?:handoff|compact|idle|resume|wrapup|summary))?(?:\.json|\.summary\.md(?:\.bak)?)$")


def prune_sessions(root, keep_session=None, days=SESSION_KEEP_DAYS, now=None):
    """Remove the per-session files of sessions with no file changed in `days` days. A session is kept whole while
    any of its files is newer; `keep_session` (the running one) is always kept. Never follows or removes a link.
    Returns the number of files removed."""
    folder = os.path.join(root, SESSIONS_DIR)
    if os.path.islink(folder) or os.path.islink(os.path.dirname(folder)) or not os.path.isdir(folder):
        return 0
    keep = safe_session_id(keep_session)
    cutoff = (time.time() if now is None else now) - days * 86400
    groups, fresh = {}, set()
    for name in os.listdir(folder):
        m = SESSION_FILE_RE.match(name)
        if not m or name.startswith("health-"):
            continue
        sid = m.group("id")
        try:
            info = os.lstat(os.path.join(folder, name))
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        groups.setdefault(sid, []).append(name)
        if info.st_mtime >= cutoff:
            fresh.add(sid)
    removed = 0
    for sid, names in groups.items():
        if sid == keep or sid in fresh:
            continue
        for name in names:
            try:
                os.remove(os.path.join(folder, name))
                removed += 1
            except OSError:
                pass
    return removed


def safe_session_id(value):
    """A file-name-safe form of the hook's session_id, or None when nothing usable is left."""
    if not isinstance(value, str):
        return None
    name = re.sub(r"[^A-Za-z0-9._-]", "_", value).lstrip(".")[:SESSION_ID_MAX]
    return name or None


def rel_path(root, prefix, path):
    """`path` as git prints it: relative to the repository top, forward slashes."""
    return prefix + os.path.relpath(path, root).replace(os.sep, "/")


def is_bookkeeping(name, skip):
    """True for a path whatsnext itself writes (it is never "work the agent did")."""
    return any(name == s or (s.endswith("/") and name.startswith(s)) for s in skip)


def status_paths(root):
    """Paths from `git status --porcelain` (untracked files one by one); None when git fails."""
    code, out = gwstatus.git(root, "-c", "core.quotepath=off", "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return None
    names = []
    for line in out.splitlines():
        name = line[3:].split(" -> ")[-1].strip().strip('"')
        if name:
            names.append(name)
    return names


def changed_since(root, base):
    """Sorted names from `git diff --name-only <base>` plus untracked files. A base git does not
    know (or none) compares against HEAD, so only uncommitted work shows."""
    names = set()
    attempts = []
    if base:
        attempts.append(("diff", "--name-only", "--end-of-options", base))
    attempts.append(("diff", "--name-only", "--end-of-options", "HEAD"))
    for args in attempts:
        code, out = gwstatus.git(root, "-c", "core.quotepath=off", *args)
        if code == 0:
            names.update(line.strip() for line in out.splitlines() if line.strip())
            break
    code, out = gwstatus.git(root, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard",
                             "--full-name")
    if code == 0:
        names.update(line.strip() for line in out.splitlines() if line.strip())
    return sorted(names)


def last_commit(path):
    """The commit on the journal's last line that has one, or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = LINE_RE.match(line)
        if m:
            commit = m.group("commit")
            return None if commit == gwstatus.NONE else commit
    return None


def dirty_digest(names):
    """A short hash of the dirty file names (not their content), so a changed set shows when the count did not move."""
    return hashlib.sha1("\n".join(sorted(names)).encode("utf-8", "replace")).hexdigest()[:6] if names else None


def last_state(path):
    """(dirty count, set digest or None) from the journal's last line, or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = STATE_RE.match(line)
        if m:
            return int(m.group("count")), m.group("set")
    return None


def format_line(when, event, commit, branch, dirty, files, digest=None):
    head = "- %s %s %s %s dirty=%d" % (when, event, commit or gwstatus.NONE, branch, dirty)
    if digest:
        head += " set=" + digest
    if not files:
        return head
    line = head + " files:"
    used = 0
    for i, name in enumerate(files):
        piece = (" " if i == 0 else ", ") + name
        more = len(files) - i - 1
        reserve = len(", +%d more" % more) if more else 0
        if len(line) + len(piece) + reserve > MAX_LINE:
            break
        line += piece
        used += 1
    rest = len(files) - used
    if rest:
        line += (", " if used else " ") + "+%d more" % rest
    return line[:MAX_LINE]


def append_line(path, item, line):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        if new:
            f.write("# Journal: %s\n\n" % item)
        f.write(line + "\n")


def write_session_state(root, session_id, event, when, item, commit, branch):
    """`.whatsnext/sessions/<session_id>.json`: when this session last wrote facts."""
    name = safe_session_id(session_id)
    if name is None:
        return None
    folder = os.path.join(root, SESSIONS_DIR)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".json")
    state = {"session_id": session_id, "last_event": event, "last_event_time": when, "item": item,
             "commit": commit, "branch": branch}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def record(root, effective, event, data=None):
    """Write the facts for `event`. Returns the journal path, or None when nothing was written.
    Errors propagate: the hook caller turns them into silence."""
    if not gwstatus.in_git(root):
        return None
    folder = gwstatus.status_folder(root, effective)
    branch = gwstatus.current_branch(root)
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), branch)
    if task is None or not gwstatus.ID_RE.match(task.id):
        return None
    journal = os.path.join(folder, "journal", task.id + ".md")
    code, out = gwstatus.git(root, "rev-parse", "--show-prefix")
    prefix = out.strip() if code == 0 else ""
    skip = (rel_path(root, prefix, journal), rel_path(root, prefix, task.path),
            rel_path(root, prefix, os.path.join(root, SESSIONS_DIR)) + "/")
    base = last_commit(journal) or gwstatus.recorded_commit(task)
    changed = [n for n in changed_since(root, base) if not is_bookkeeping(n, skip)]
    dirty = status_paths(root)
    dirty_names = [n for n in (dirty or []) if not is_bookkeeping(n, skip)]
    dirty_count = len(dirty_names)
    when = gwstatus.stamp_time()
    commit = gwstatus.current_commit(root)
    append_line(journal, task.id, format_line(when, event, commit, branch, dirty_count, changed, dirty_digest(dirty_names)))
    session_id = data.get("session_id") if isinstance(data, dict) else None
    write_session_state(root, session_id, event, when, task.id, commit, branch)
    gwstatus.stamp_file(root, folder, effective, task.id)
    return journal
