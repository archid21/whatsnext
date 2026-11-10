"""Progress files, one per task (ADR-0002) and the freshness check.

One file per task: `<paths.progress>/<task-id>.md`. The header fields are
`- **Name:** value` lines between the title line and the first `## ` heading.
The agent edits the sections itself; `progress stamp` rewrites only header fields.
"""

import argparse
import json
import os
import re
import subprocess
import sys

from . import backend as gwbackend
from . import config as gwconfig
from . import redact as gwredact
from .util import now_utc, write_atomic

PLACEHOLDER = "(to fill in)"
FIELD_RE = re.compile(r"^- \*\*([^:*]+):\*\*[ \t]*(.*?)\s*$")
H2_RE = re.compile(r"^## (.*?)\s*$")
STATES = ("active", "blocked", "parked", "review", "done")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
H1_RE = re.compile(r"^# (.*?)\s*$")
MAX_LISTED_FILES = 5
NONE = "none"
FORMAT = 2  # ADR-0002: every progress file starts with `format: 2`
FORMAT_RE = re.compile(r"^format:\s*(\d+)\s*$")
MARKS = ("confirmed", "auto", "facts")  # ADR-0002: trust marks
NOTE_RE = re.compile(r"^(confirmed|auto|facts)\b")
SINCE_WRAP_UP = "Since wrap-up"

TEMPLATE = """format: 2

# %(id)s: %(title)s

- **State:** active
- **Agent:** %(agent)s
- **Branch:** %(branch)s
- **Commit:** %(commit)s
- **Updated:** %(updated)s
- **Files:** none
- **Decisions:** none
- **Note:** facts (%(updated)s)

## Next action

%(placeholder)s

## Goal

## Done

## In progress

## Open questions
"""


def stamp_time():
    return now_utc().strftime("%Y-%m-%dT%H:%MZ")


# ---- git -------------------------------------------------------------------


def git(root, *args):
    """(return code, stdout) of a git command in `root`; (1, "") when git cannot run."""
    try:
        out = subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return out.returncode, out.stdout


def in_git(root):
    return git(root, "rev-parse", "--is-inside-work-tree")[0] == 0


def current_branch(root):
    """Branch name; "(detached)" on a detached HEAD; None outside git."""
    if not in_git(root):
        return None
    code, out = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    return out.strip() if code == 0 and out.strip() else "(detached)"


def current_commit(root):
    """Short HEAD hash, or None outside git or before the first commit."""
    code, out = git(root, "rev-parse", "--short", "HEAD")
    return out.strip() if code == 0 and out.strip() else None


# ---- reading files ---------------------------------------------------------


class Task(object):
    """One progress file, read as lines. Nothing here writes."""

    def __init__(self, root, path):
        self.path = path
        self.rel = gwconfig.display_path(path, root)
        self.id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            self.text = f.read()
        self.lines = self.text.split("\n")
        self.title = ""
        self.fields = {}  # lower name -> value
        self.sections = {}  # lower name -> body text
        self._parse()

    def _parse(self):
        current = None
        body = []
        seen_h1 = False
        self.format = 1
        for line in self.lines:
            line = line.rstrip("\r")
            fmt = FORMAT_RE.match(line) if not seen_h1 and current is None else None
            if fmt:
                self.format = int(fmt.group(1))
                continue
            h2 = H2_RE.match(line)
            if h2:
                if current is not None:
                    self.sections.setdefault(current, "\n".join(body).strip())
                current, body = h2.group(1).strip().lower(), []
            elif current is not None:
                body.append(line)
            elif not seen_h1:
                if line.strip():
                    seen_h1 = True
                    m = H1_RE.match(line)
                    text = m.group(1) if m else line.strip()
                    _head, sep, rest = text.partition(": ")
                    self.title = rest if sep else text
            else:
                m = FIELD_RE.match(line)
                if m:
                    self.fields.setdefault(m.group(1).strip().lower(), m.group(2))
        if current is not None:
            self.sections.setdefault(current, "\n".join(body).strip())

    def field(self, name):
        return self.fields.get(name.lower(), "").strip()

    @property
    def state(self):
        words = self.field("state").split()
        return words[0].lower() if words else ""

    @property
    def note_mark(self):
        """"confirmed", "auto" or "facts" from the Note field; "" when missing."""
        m = NOTE_RE.match(self.field("note").lower())
        return m.group(1) if m else ""

    def section(self, name):
        """Section text, or "" when missing, empty or still the placeholder."""
        text = self.sections.get(name.lower(), "")
        return "" if text == PLACEHOLDER else text

    def file_list(self):
        value = self.field("files")
        if not value or value.lower() == NONE:
            return []
        return [f.strip() for f in value.split(",") if f.strip()]


def status_folder(root, effective):
    return os.path.join(root, effective.get("paths.progress"))


def task_path(folder, task_id):
    return os.path.join(folder, task_id + ".md")


def load_tasks(root, folder):
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.endswith(".md") and name.lower() != "readme.md" and os.path.isfile(path):
            out.append(Task(root, path))
    return out


def env_session():
    """The session id `WHATSNEXT_SESSION` names (the Claude Code SessionStart hook exports it), or None."""
    value = os.environ.get("WHATSNEXT_SESSION", "").strip()
    return value or None


def session_ids(root, session):
    """The ids of the items whose claim names `session` (ADR-0020). Empty without a session or a root."""
    if not session or not root:
        return set()
    from . import claims as gwclaims  # claims imports this module
    return {i for i, c in gwclaims.read_all(root).items() if c.get("session") == session}


def active_task(tasks, branch, session=None, root=None):
    """The active task for this checkout: the active item this session claimed first (ADR-0020), else the branch
    match, then the latest Updated. Without a session id, or when this session holds no active item, only the
    branch rule applies."""
    active = [t for t in tasks if t.state == "active"]
    if not active:
        return None
    mine_ids = session_ids(root, session)
    mine = [t for t in active if t.id in mine_ids]
    pool = mine or active
    return sorted(pool, key=lambda t: (branch is not None and t.field("branch") == branch,
                                       t.field("updated"), t.id))[-1]


def branch_task(tasks, branch, session=None, root=None):
    """The active task whose recorded Branch is `branch`, or None. Unlike `active_task` there is no
    fallback to another branch's item: a hook that writes must only touch its own branch's item.
    A missing or `none` Branch never matches. Among those, the item this session claimed comes first
    (ADR-0020), else the latest Updated."""
    if not branch:
        return None
    found = [t for t in tasks if t.state == "active" and t.field("branch") not in ("", NONE)
             and t.field("branch") == branch]
    mine_ids = session_ids(root, session) if found else set()
    pool = [t for t in found if t.id in mine_ids] or found
    return sorted(pool, key=lambda t: (t.field("updated"), t.id))[-1] if pool else None


# ---- freshness (S1) --------------------------------------------------------


COMMIT_RE = re.compile(r"[0-9a-fA-F]{4,40}")


def recorded_commit(task):
    """The progress file's Commit as a hex id, or None. Anything else (none, a typo, an `--option`)
    is never passed to git: the file is repo content, so it must not become a git argument."""
    commit = task.field("commit")
    return commit if COMMIT_RE.fullmatch(commit or "") else None


def changed_files(root, base, listed):
    """Listed files that differ from `base` in the working tree (committed, staged, unstaged or new)."""
    names = set()
    for args in (("diff", "--name-only", "--end-of-options", base), ("ls-files", "--others", "--exclude-standard")):
        code, out = git(root, *args)
        if code == 0:
            names.update(line.strip() for line in out.splitlines() if line.strip())
    hits = []
    for f in listed:
        stem = f.rstrip("/")
        if any(n == stem or n.startswith(stem + "/") for n in names):
            hits.append(f)
    return hits


def freshness(root, task):
    """Warning lines (without the frame) for how the code moved since `task` was written."""
    commit = recorded_commit(task)
    if commit is None or not in_git(root):
        return []
    lines = []
    recorded = task.field("branch")
    branch = current_branch(root)
    if recorded and recorded.lower() != NONE and branch != recorded:
        lines.append("branch is now %s (status says %s)" % (branch, recorded))
    if git(root, "merge-base", "--is-ancestor", "--end-of-options", commit, "HEAD")[0] == 0:
        code, out = git(root, "rev-list", "--count", "--end-of-options", commit + "..HEAD")
        count = int(out.strip()) if code == 0 and out.strip().isdigit() else 0
        if count:
            lines.append("%d new commit%s since %s" % (count, "" if count == 1 else "s", commit))
        base = commit
    else:
        lines.append("the recorded commit %s is not in this history" % commit)
        base = "HEAD"  # only uncommitted changes can be compared
    files = changed_files(root, base, task.file_list())
    if files:
        more = len(files) - MAX_LISTED_FILES
        lines.append("files changed: %s%s" % (", ".join(files[:MAX_LISTED_FILES]),
                                              " and %d more" % more if more > 0 else ""))
    return lines


def freshness_block(root, task):
    """The whole warning block, or "" when nothing changed."""
    found = freshness(root, task)
    if not found:
        return ""
    head = "Changed since this progress file was written (%s):" % (task.field("updated") or "unknown time")
    return "\n".join([head] + ["- " + line for line in found] + ["Check these before resuming."])


# ---- writing ---------------------------------------------------------------


def header_end(lines):
    for i, line in enumerate(lines):
        if H2_RE.match(line.rstrip("\r")):
            return i
    return len(lines)


def set_field(lines, name, value):
    """Set `- **name:** value` in the header, adding it after the last field when missing."""
    end = header_end(lines)
    last = None
    for i in range(end):
        m = FIELD_RE.match(lines[i].rstrip("\r"))
        if m:
            last = i
            if m.group(1).strip().lower() == name.lower():
                tail = "\r" if lines[i].endswith("\r") else ""
                lines[i] = "- **%s:** %s%s" % (name, value, tail)
                return
    new = "- **%s:** %s" % (name, value)
    if last is not None:
        lines.insert(last + 1, new)
    else:
        lines[end:end] = [new, ""] if end == len(lines) else [new]


def remove_field(lines, name):
    """Delete the header field `name` when it is there."""
    for i in range(header_end(lines)):
        m = FIELD_RE.match(lines[i].rstrip("\r"))
        if m and m.group(1).strip().lower() == name.lower():
            del lines[i]
            return


def field_value(lines, name):
    """The header field's value, or None."""
    for i in range(header_end(lines)):
        m = FIELD_RE.match(lines[i].rstrip("\r"))
        if m and m.group(1).strip().lower() == name.lower():
            return m.group(2)
    return None


class FormatError(ValueError):
    pass


def check_format(lines, path):
    """Refuse a file written by a newer whatsnext; add `format: 2` to one that has no format line."""
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = FORMAT_RE.match(line.rstrip("\r"))
        if m is None:
            lines[i:i] = ["format: %d" % FORMAT, ""]
        elif int(m.group(1)) > FORMAT:
            raise FormatError("%s is format %s; this whatsnext knows format %d. Update whatsnext."
                              % (path, m.group(1), FORMAT))
        return
    lines[0:0] = ["format: %d" % FORMAT, ""]


def set_section(lines, name, body):
    """Replace the body of `## name`, adding the section at the end when missing."""
    start = None
    for i, line in enumerate(lines):
        m = H2_RE.match(line.rstrip("\r"))
        if m and start is None and m.group(1).strip().lower() == name.lower():
            start = i
        elif m and start is not None:
            lines[start + 1:i] = ["", body, ""]
            return
    if start is not None:
        lines[start + 1:] = ["", body, ""]
        return
    while lines and not lines[-1].strip():
        lines.pop()
    lines.extend(["", "## " + name, "", body, ""])


def get_section(lines, name):
    start = None
    for i, line in enumerate(lines):
        m = H2_RE.match(line.rstrip("\r"))
        if m and start is None and m.group(1).strip().lower() == name.lower():
            start = i
        elif m and start is not None:
            return "\n".join(lines[start + 1:i]).strip()
    return "\n".join(lines[start + 1:]).strip() if start is not None else ""


def write_next(root, folder, task_id, text, mark="confirmed"):
    """Write the Next action with a trust mark. An auto write never replaces a confirmed one:
    it goes to `## Since wrap-up` instead (ADR-0002). Returns (display path, where)."""
    path = task_path(folder, task_id)
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    check_format(lines, path)
    note = (field_value(lines, "Note") or "").lower()
    when = stamp_time()
    if mark == "auto" and note.startswith("confirmed"):
        old = get_section(lines, SINCE_WRAP_UP)
        entry = "- %s: Next: %s" % (when, text)
        set_section(lines, SINCE_WRAP_UP, (old + "\n" + entry).strip())
        where = SINCE_WRAP_UP
    else:
        set_section(lines, "Next action", text)
        set_field(lines, "Note", "%s (%s)" % (mark, when))
        where = "Next action"
    set_field(lines, "Updated", when)
    write_text(path, "\n".join(lines))
    return gwconfig.display_path(path, root), where


HISTORY = "History"


def add_history(root, folder, task_id, title, entry, state=None):
    """P-59: add `- <UTC> <entry>` to the task's `## History` section, which keeps what `plan edit` and
    `plan reopen` changed (old titles, done means and evidence). A task with no progress file gets one, parked so it
    never becomes the active task. `state` also sets State. Returns the display path."""
    path = task_path(folder, task_id)
    when = stamp_time()
    if not os.path.isfile(path):
        text = TEMPLATE % {"id": task_id, "title": " ".join(title.split()) or task_id, "agent": "unknown",
                           "branch": NONE, "commit": NONE, "updated": when, "placeholder": PLACEHOLDER}
        text = text.replace("- **State:** active", "- **State:** parked", 1)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_text(path, text)
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    check_format(lines, path)
    old = get_section(lines, HISTORY)
    line = "- %s %s" % (when, " ".join(entry.split()))
    set_section(lines, HISTORY, (old + "\n" + line).strip())
    if state:
        set_field(lines, "State", state)
    set_field(lines, "Updated", when)
    write_text(path, "\n".join(lines))
    return gwconfig.display_path(path, root)


def set_note(folder, task_id, mark, when=None):
    """Set the Note trust mark of an existing progress file (`confirmed (<time>)`), refresh Updated.
    Returns False when the task has no progress file. Not for `auto`: use write_next, which guards."""
    path = task_path(folder, task_id)
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    check_format(lines, path)
    when = when or stamp_time()
    set_field(lines, "Note", "%s (%s)" % (mark, when))
    set_field(lines, "Updated", when)
    write_text(path, "\n".join(lines))
    return True


def write_text(path, text, warn=True):
    """Write a progress file: private text removed first, a secret-looking text warned about (ADR-0002)."""
    text = gwredact.clean(text, os.path.basename(path), quiet=not warn)
    write_atomic(path, text)


def emit(effective, task_id, rel, action):
    try:
        gwbackend.get_backend(effective).emit("status.write", {"task": task_id, "path": rel, "action": action})
    except (gwbackend.BackendError, ValueError, OSError) as e:
        print("warning: backend event status.write not delivered: %s" % e, file=sys.stderr)


def bad_id(task_id):
    if ID_RE.match(task_id):
        return None
    return "task id %r must use letters, digits, dot, dash or underscore (for example P-13)." % task_id


def cmd_new(root, folder, effective, args):
    problem = bad_id(args.task_id)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    path = task_path(folder, args.task_id)
    rel = gwconfig.display_path(path, root)
    if os.path.exists(path):
        print("%s already exists. Edit it, or run `progress stamp %s`." % (rel, args.task_id), file=sys.stderr)
        return 1
    title = " ".join(args.title.split())
    if not title:
        print("--title must not be empty.", file=sys.stderr)
        return 1
    agent = " ".join((args.agent or os.environ.get("WHATSNEXT_AGENT") or os.environ.get("GROUNDWORK_AGENT") or "").split()) or "unknown"
    write_text(path, TEMPLATE % {
        "id": args.task_id, "title": title, "agent": agent,
        "branch": current_branch(root) or NONE, "commit": current_commit(root) or NONE,
        "updated": stamp_time(), "placeholder": PLACEHOLDER,
    })
    print("created " + rel)
    emit(effective, args.task_id, rel, "new")
    return 0


def stamp_file(root, folder, effective, task_id, state=None, files=None, agent=None):
    """Record branch, commit and time (and optionally state, files, agent) in a progress file.

    Also drops the "Ended without wrap-up" note and refreshes the task's checkout claim,
    if one exists. Returns the display path.
    """
    path = task_path(folder, task_id)
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    set_field(lines, "Branch", current_branch(root) or NONE)
    set_field(lines, "Commit", current_commit(root) or NONE)
    set_field(lines, "Updated", stamp_time())
    check_format(lines, path)
    note = field_value(lines, "Note")
    if not note or NOTE_RE.match(note.lower()) is None or note.lower().startswith("facts"):
        set_field(lines, "Note", "facts (%s)" % stamp_time())
    remove_field(lines, "Ended without wrap-up")  # the session-end note (session.py) is out of date now
    if state:
        set_field(lines, "State", state)
    if agent:
        set_field(lines, "Agent", agent)
    if files is not None:
        names = [f.strip() for f in files.split(",") if f.strip()]
        set_field(lines, "Files", ", ".join(names) if names else NONE)
    write_text(path, "\n".join(lines))
    try:
        from . import claims

        claims.touch(root, task_id)
    except Exception:  # a claim problem must not fail a status write
        pass
    return gwconfig.display_path(path, root)


def cmd_stamp(root, folder, effective, args):
    path = None if bad_id(args.task_id) else task_path(folder, args.task_id)
    if not path or not os.path.isfile(path):
        print("no progress file for %s. Create it: `progress new %s --title \"...\"`." % (args.task_id, args.task_id),
              file=sys.stderr)
        return 1
    rel = stamp_file(root, folder, effective, args.task_id, state=args.state, files=args.files)
    print("stamped " + rel)
    emit(effective, args.task_id, rel, "stamp")
    return 0


def cmd_next(root, folder, effective, args):
    path = None if bad_id(args.task_id) else task_path(folder, args.task_id)
    if not path or not os.path.isfile(path):
        print("no progress file for %s." % args.task_id, file=sys.stderr)
        return 1
    text = " ".join(args.text.split())
    if not text:
        print("the next action must not be empty.", file=sys.stderr)
        return 1
    rel, where = write_next(root, folder, args.task_id, text, "auto" if args.auto else "confirmed")
    print("wrote %s in %s" % (where, rel))
    emit(effective, args.task_id, rel, "next")
    return 0


def cmd_show(root, folder, effective, args):
    tasks = load_tasks(root, folder)
    if args.task_id:
        task = next((t for t in tasks if t.id == args.task_id), None)
        if task is None:
            print("no progress file for %s." % args.task_id, file=sys.stderr)
            return 1
    else:
        task = active_task(tasks, current_branch(root), env_session(), root)
        if task is None:
            print("No active task.")
            return 0
    sys.stdout.write(task.text if task.text.endswith("\n") else task.text + "\n")
    return 0


def cmd_list(root, folder, effective, args):
    tasks = load_tasks(root, folder)
    if not tasks:
        print("No progress files in %s." % effective.get("paths.progress"))
        return 0
    rows = [(t.id, t.state or "?", t.field("updated") or "?", t.field("branch") or "?") for t in tasks]
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    for r in rows:
        print("  ".join(r[i].ljust(widths[i]) for i in range(3)) + "  " + r[3])
    return 0


def cmd_packet(root, folder, effective, args):
    from . import packet

    result = packet.build(root, effective)
    text = result["text"] + "\n" if result else ""  # exactly what the hook prints
    if args.json:
        print(json.dumps({"text": text, "chars": len(text),
                          "sections_included": result["included"] if result else [],
                          "sections_pointed": result["pointed"] if result else []}, indent=2))
    else:
        sys.stdout.write(text)
    return 0


def cmd_resume(root, folder, effective, args):
    """P-57: the resume note for one task, from its newest handoff (the handoff note or docs/project/handoffs/).
    It only reads and prints: it claims nothing and switches no branch."""
    from . import packet
    from . import wrapup

    problem = bad_id(args.task_id)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    task = next((t for t in load_tasks(root, folder) if t.id == args.task_id), None)
    if task is None:
        print("no progress file for %s. Run `whatsnext progress list` to see the tasks." % args.task_id,
              file=sys.stderr)
        return 1
    found = wrapup.latest_handoff(root, effective, task.id)
    result = packet.build(root, effective, task_id=task.id, handoff=found[0] if found else None)
    if result is None:
        print("the progress module is off, or this is not a whatsnext project.", file=sys.stderr)
        return 1
    lines = [result["text"]]
    want, here = task.field("branch"), current_branch(root)
    if want and want.lower() != "unknown" and here and here != want:
        line = "Branch: you are on %s; %s is on %s." % (packet.clean(here), task.id, packet.clean(want))
        if git(root, "rev-parse", "--verify", "-q", "refs/heads/" + want)[0] != 0:
            line += " That branch no longer exists here."
        elif packet.safe_command("git switch " + want) and not want.startswith("-"):
            line += " Run: git switch " + want  # the name is repository data: shown only when it is a plain word
        lines.append(line)
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def cmd_capture(root, folder, effective, args):
    from . import capture

    return capture.run(root, folder, effective, args)


def build_parser():
    parser = argparse.ArgumentParser(prog="whatsnext progress", description="Progress files: one per task.")
    sub = parser.add_subparsers(dest="action")
    sub.required = True
    new = sub.add_parser("new", help="create a progress file from the template")
    new.add_argument("task_id")
    new.add_argument("--title", required=True)
    new.add_argument("--agent", help="default: $WHATSNEXT_AGENT, then $GROUNDWORK_AGENT, else unknown")
    stamp = sub.add_parser("stamp", help="record the branch, commit and time (and optionally state and files)")
    stamp.add_argument("task_id")
    stamp.add_argument("--state", choices=STATES)
    stamp.add_argument("--files", help="comma-separated list that replaces the Files field")
    nxt = sub.add_parser("next", help="set the Next action (marked confirmed; --auto for a model-written one)")
    nxt.add_argument("task_id")
    nxt.add_argument("text")
    nxt.add_argument("--auto", action="store_true",
                     help="mark it auto; it goes to '## Since wrap-up' when the note is confirmed")
    show = sub.add_parser("show", help="print a progress file (default: the active task)")
    show.add_argument("task_id", nargs="?")
    sub.add_parser("list", help="list progress files")
    capture = sub.add_parser("capture", help="store a plan-mode plan and write its steps (ADR-0006)")
    capture.add_argument("task_id", nargs="?", help="default: the active task")
    capture.add_argument("--status", required=True, choices=("shown", "approved", "unapproved"))
    capture.add_argument("--agent", help="default: $WHATSNEXT_AGENT, then $GROUNDWORK_AGENT, else unknown")
    capture.add_argument("--file", help="the plan text (default: stdin); only for --status shown")
    resume = sub.add_parser("resume", help="print the resume note for one task, from its newest handoff")
    resume.add_argument("task_id")
    note = sub.add_parser("resume-note", help="print the resume note the session-start hook adds")
    note.add_argument("--json", action="store_true")
    return parser


def run(argv, cwd=None):
    args = build_parser().parse_args(argv)
    root = gwconfig.find_root(cwd)
    effective = gwconfig.load(root)
    folder = status_folder(root, effective)
    handler = {"new": cmd_new, "stamp": cmd_stamp, "show": cmd_show, "list": cmd_list, "next": cmd_next, "capture": cmd_capture,
               "resume-note": cmd_packet, "resume": cmd_resume}
    try:
        return handler[args.action](root, folder, effective, args)
    except FormatError as e:
        print(str(e), file=sys.stderr)
        return 1
