"""The handoff-versus-git cross-check (P-15): do the files the note's "What changed" names match what git shows?

A model wrote the note, so a file it names may not have changed, and a file that changed may be missing from it.
This compares the two lists. It reads the note and git; it changes nothing and calls no model.
"""

import os
import re

from . import journal as gwjournal
from . import status as gwstatus

PATH_RE = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?|[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*\.[A-Za-z][A-Za-z0-9]{0,5}\b")
MAX_NAMES = 10  # how many names the sidecar and the note list


def named_paths(body):
    """The file paths named in the note's `## What changed` section, in order, without repeats."""
    lines, grab, out = body.splitlines(), False, []
    for line in lines:
        if line.startswith("## "):
            grab = line[3:].strip().lower() == "what changed"
            continue
        if not grab:
            continue
        for token in PATH_RE.findall(re.sub(r"https?://\S+", " ", line)):
            token = token.strip("./") if token.startswith("./") else token
            if token and not re.fullmatch(r"\d+(\.\d+)+", token) and token not in out:
                out.append(token)
    return out


def same(a, b):
    """A named path matches a changed one when they are equal, or one ends with the other after a slash."""
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a) or (a != b and b.startswith(a + "/"))


def changed_paths(root, effective, task, handoff):
    """Files changed since the progress file's commit, plus uncommitted ones; whatsnext's own files left out."""
    if not gwstatus.in_git(root):
        return []
    code, out = gwstatus.git(root, "rev-parse", "--show-prefix")
    prefix = out.strip() if code == 0 else ""
    folder = gwstatus.status_folder(root, effective)
    skip = [gwjournal.rel_path(root, prefix, handoff), gwjournal.rel_path(root, prefix, os.path.dirname(handoff)) + "/handoffs/",
            gwjournal.rel_path(root, prefix, folder) + "/", gwjournal.rel_path(root, prefix, os.path.join(root, gwjournal.SESSIONS_DIR)) + "/"]
    base = gwstatus.recorded_commit(task) if task is not None else None
    return [n for n in gwjournal.changed_since(root, base) if not gwjournal.is_bookkeeping(n, skip)]


def cross_check(root, effective, handoff, task):
    """{"named_not_changed": [...], "changed_not_named": [...]}, each at most MAX_NAMES long, or None when the note
    cannot be read or git is not there."""
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except OSError:
        return None
    if not gwstatus.in_git(root):
        return None
    named = named_paths(body)
    changed = changed_paths(root, effective, task, handoff)
    return {"named_not_changed": [n for n in named if not any(same(n, c) for c in changed)][:MAX_NAMES],
            "changed_not_named": [c for c in changed if not any(same(n, c) for n in named)][:MAX_NAMES]}


def note_line(check):
    """The line for the resume note, or None when the two lists agree."""
    if not isinstance(check, dict):
        return None
    parts = []
    if check.get("named_not_changed"):
        parts.append("named, not changed in git: " + ", ".join(check["named_not_changed"][:4]))
    if check.get("changed_not_named"):
        parts.append("changed, not named: " + ", ".join(check["changed_not_named"][:4]))
    return "Handoff check: " + "; ".join(parts) + "." if parts else None
