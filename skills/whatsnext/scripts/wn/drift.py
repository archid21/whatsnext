"""The drift note (ADR-0028, P-73): one note when a turn changes files outside the claimed item's scope.

Scope. When the item's progress file has a `Files:` line other than `none`, the scope is those paths. Otherwise the
scope is learned: the folders of the files changed in the item's first LEARN_TURNS turns that change files. A file is in
scope when it is in a listed file's folder or under a listed folder. Files under the progress, plans and handoff
folders of the project (`docs/project/` by default) never count.

State is per session, in the git-ignored `.whatsnext/sessions/<session>.drift.json`:

    {"items": {"P-12": {"turns": 2, "folders": ["src"], "seen": ["src/a.py"], "noted": [], "dismissed": []}},
     "pending": {"item": "P-12", "files": ["x.py"], "text": "..."} or null}

`check` runs at turn end. It never blocks, never writes PLAN.md and never raises: any error means no note.
`plan.driftNote` is `on` (default) or `off`.
"""

import json
import os
import re

from . import journal as gwjournal
from . import status as gwstatus
from .util import write_atomic

LEARN_TURNS = 3
LIST_NAMES = 3
SUFFIX = ".drift.json"


def drift_path(root, session):
    name = gwjournal.safe_session_id(session)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + SUFFIX) if name else None


def load(path):
    """The state dict at `path`; an empty one when the file is missing or not what this module wrote."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    if not isinstance(data.get("pending"), dict):
        data["pending"] = None
    return data


def save(path, state):
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)):
        return
    write_atomic(path, json.dumps(state, indent=2) + "\n", newline=None)


# ---- scope -----------------------------------------------------------------


def folder_of(name):
    return os.path.dirname(name.replace("\\", "/")).strip("/")


def listed_folders(root, names):
    """The folders for the paths of a `Files:` line: a file counts as its folder; a trailing slash or a folder on disk
    counts as itself."""
    out = []
    for name in names:
        clean = name.replace("\\", "/").strip()
        if not clean:
            continue
        if clean.endswith("/") or os.path.isdir(os.path.join(root, clean)):
            out.append(clean.strip("/"))
        else:
            out.append(folder_of(clean))
    return out


def in_scope(name, folders):
    """True when `name` is in one of `folders` or under one (the project root folder "" matches root files only)."""
    here = folder_of(name)
    for folder in folders:
        if here == folder or (folder and here.startswith(folder + "/")):
            return True
    return False


def ignored_prefixes(root, effective):
    """Paths that never count: `docs/project/`, `.whatsnext/` and wherever the settings put the plan, progress files, plans and handoff."""
    out = ["docs/project/", ".whatsnext/"]
    for key, is_folder in (("paths.plan", False), ("paths.progress", True), ("paths.plans", True),
                           ("paths.handoff", False)):
        try:
            value = str(effective.get(key)).replace("\\", "/")
        except Exception:
            continue
        while value.startswith("./"):
            value = value[2:]
        value = value.strip("/")
        if value:
            out.append(value + "/" if is_folder else value)
    return out


def is_ignored(name, prefixes):
    return any(name == p or (p.endswith("/") and name.startswith(p)) for p in prefixes)


# ---- the note --------------------------------------------------------------


def note_text(item, files):
    shown = ", ".join(files[:LIST_NAMES]) + (", …" if len(files) > LIST_NAMES else "")
    return ("%d file%s changed outside %s (%s). Add them to %s (`progress stamp %s --files …`), "
            "or plan them as new work?" % (len(files), "" if len(files) == 1 else "s", item, shown, item, item))


def pending_note(root, session):
    """The unanswered note for `session` as {"item", "files", "text"}, or None. Never raises."""
    try:
        path = drift_path(root, session)
        if not path or not os.path.isfile(path):
            return None
        pending = load(path)["pending"]
        if pending and isinstance(pending.get("text"), str) and pending["text"]:
            return pending
    except Exception:
        pass
    return None


def claimed_item(root, effective, session):
    """The active item this session claimed on this branch, or None."""
    if not session:
        return None
    folder = gwstatus.status_folder(root, effective)
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root), session, root)
    if task is None or not gwstatus.ID_RE.match(task.id) or task.id not in gwstatus.session_ids(root, session):
        return None
    return task


def turn_files(root, task, folder, state_item):
    """(changed now, names new since the last check), bookkeeping files left out."""
    code, out = gwstatus.git(root, "rev-parse", "--show-prefix")
    prefix = out.strip() if code == 0 else ""
    journal = os.path.join(folder, "journal", task.id + ".md")
    skip = (gwjournal.rel_path(root, prefix, journal), gwjournal.rel_path(root, prefix, task.path),
            gwjournal.rel_path(root, prefix, os.path.join(root, gwjournal.SESSIONS_DIR)) + "/")
    base = gwjournal.last_commit(journal) or gwstatus.recorded_commit(task)
    changed = [n for n in gwjournal.changed_since(root, base) if not gwjournal.is_bookkeeping(n, skip)]
    seen = set(state_item.get("seen") or [])
    return changed, [n for n in changed if n not in seen]


def check(root, effective, data):
    """Run the check for this turn end. Returns the pending note's text when a new note was made, else "".
    Never raises."""
    try:
        return _check(root, effective, data)
    except Exception:
        return ""


def _check(root, effective, data):
    if effective.get("plan.driftNote") == "off" or not gwstatus.in_git(root):
        return ""
    session = data.get("session_id") if isinstance(data.get("session_id"), str) else None
    path = drift_path(root, session)
    task = claimed_item(root, effective, session) if path else None
    if task is None:
        return ""
    folder = gwstatus.status_folder(root, effective)
    state = load(path)
    item = state["items"].get(task.id)
    if not isinstance(item, dict):
        item = {}
    for key in ("folders", "seen", "noted", "dismissed"):
        if not isinstance(item.get(key), list):
            item[key] = []
    if not isinstance(item.get("turns"), int):
        item["turns"] = 0
    state["items"][task.id] = item
    changed, new = turn_files(root, task, folder, item)
    prefixes = ignored_prefixes(root, effective)
    new = [n for n in new if not is_ignored(n, prefixes)]
    item["seen"] = [n for n in changed if not is_ignored(n, prefixes)]
    note = ""
    listed = task.file_list()
    if listed:
        scope = listed_folders(root, listed)
    else:
        scope = list(item["folders"])
        if new and item["turns"] < LEARN_TURNS:
            item["turns"] += 1
            for name in new:
                folder_name = folder_of(name)
                if folder_name not in item["folders"]:
                    item["folders"].append(folder_name)
            new = []  # a learning turn is trusted to be on scope
        elif item["turns"] < LEARN_TURNS:
            new = []
    out = [n for n in new if not in_scope(n, scope) and n not in item["noted"] and n not in item["dismissed"]]
    if out:
        item["noted"].extend(out)
        text = note_text(task.id, out)
        state["pending"] = {"item": task.id, "files": out, "text": text}
        note = text
    save(path, state)
    return note


# ---- answers ---------------------------------------------------------------


def session_files(root):
    folder = os.path.join(root, gwjournal.SESSIONS_DIR)
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(SUFFIX))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names if not os.path.islink(os.path.join(folder, n))]


def clear(root, item=None, session=None, dismiss=False):
    """Clear pending notes: of `session`'s file when given, else every session's; only those for `item` when given.
    With `dismiss`, the files of the cleared note are never noted again. Returns the number cleared. Never raises."""
    cleared = 0
    try:
        path = drift_path(root, session) if session else None
        paths = [path] if path else session_files(root)
        for p in paths:
            if not p or not os.path.isfile(p):
                continue
            state = load(p)
            pending = state["pending"]
            if not pending or (item and pending.get("item") != item):
                continue
            if dismiss:
                entry = state["items"].get(pending.get("item"))
                if isinstance(entry, dict):
                    entry.setdefault("dismissed", [])
                    entry["dismissed"].extend(f for f in pending.get("files") or [] if f not in entry["dismissed"])
            state["pending"] = None
            save(p, state)
            cleared += 1
    except Exception:
        pass
    return cleared
