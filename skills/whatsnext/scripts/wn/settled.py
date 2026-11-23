"""The settled list (ADR-0036): `docs/project/SETTLED.md`, choices already made, so a later session does not reopen them.

One line each: `- <kind>: <text> (<source>)` with kind `dropped` (an approach tried and rejected), `use` (a tool or
approach that must be used) or `expected` (recurring behavior that looks like a problem and is not). The source is
an ADR path or a handoff note path. Lines are copied from the `## Settled` section of the handoff note by code, after
a wrap-up; whatsnext writes no new rule and makes no model call. The file is append-only here: oldest first, so the
resume note shows the end of it. Text goes through `mask_secrets` before it is written.
"""

import os
import re

from . import redact as gwredact
from .util import write_atomic

SETTLED_PATH = "docs/project/SETTLED.md"
KINDS = ("dropped", "use", "expected")
MAX_LINE_TEXT = 300  # characters of one line's text; a longer line is cut
HEADER = (
    "# Settled\n\n"
    "Choices already made. Do not reopen them without the user. Copied from the handoff note's `## Settled` section "
    "after a wrap-up. Each line: `- <kind>: <text> (<source>)`. `dropped`: tried and rejected. `use`: must be used. "
    "`expected`: looks like a problem and is not.\n\n"
)
LINE_RE = re.compile(r"^\s*[-*]\s+(%s)\s*:\s*(.+?)\s*$" % "|".join(KINDS), re.IGNORECASE)
SOURCE_RE = re.compile(r"^(.*\S)\s+\(([^()]+)\)$")


def path(root):
    return os.path.join(root, *SETTLED_PATH.split("/"))


def norm(text):
    """The key two lines are compared by: lower case, white space collapsed."""
    return " ".join(text.lower().split())


def split_source(rest):
    """(text, source) for `text (source)`; the source is a path (has `/` or ends in `.md`), else it stays in the text."""
    m = SOURCE_RE.match(rest)
    if m:
        src = m.group(2).strip()
        if src and ("/" in src or src.lower().endswith(".md")):
            return m.group(1).strip(), src
    return rest, None


def parse_line(line):
    """(kind, text, source or None) for a valid settled line, else None. `none` and malformed lines give None."""
    m = LINE_RE.match(line or "")
    if not m:
        return None
    text, source = split_source(m.group(2))
    text = " ".join(text.split())
    if not text or text.strip(" .").lower() == "none":
        return None
    return m.group(1).lower(), text, source


def read_lines(root):
    """The file's valid lines, oldest first, as (kind, text, source)."""
    try:
        with open(path(root), encoding="utf-8", errors="replace") as f:
            body = f.read()
    except OSError:
        return []
    found = []
    for line in body.split("\n"):
        got = parse_line(line)
        if got:
            found.append((got[0], got[1], got[2] or ""))
    return found


def format_line(kind, text, source):
    return "- %s: %s (%s)" % (kind, text, source)


def add_from_note(root, note_body, note_rel):
    """Append the new valid lines of the note's `## Settled` section to SETTLED.md; returns how many were added.
    A line with no source gets `note_rel`. A line already in the file (same kind and text, any case or spacing) is
    skipped. The file is created with a short header when missing and not touched when nothing is new."""
    from . import status as gwstatus
    section = gwstatus.get_section(note_body.split("\n"), "Settled")
    if not section:
        return 0
    target = path(root)
    if os.path.islink(target):  # a link could point outside the project
        return 0
    have = {(k, norm(t)) for k, t, _s in read_lines(root)}
    new = []
    for raw in section.split("\n"):
        got = parse_line(raw)
        if got is None:
            continue
        kind, text, source = got
        text = gwredact.mask_secrets(text, emails=True)
        text = " ".join(text.split())[:MAX_LINE_TEXT].rstrip()
        source = gwredact.mask_secrets(source or note_rel, emails=True).strip() or note_rel
        key = (kind, norm(text))
        if not text or key in have:
            continue
        have.add(key)
        new.append(format_line(kind, text, source))
    if not new:
        return 0
    try:
        with open(target, encoding="utf-8", errors="replace") as f:
            old = f.read()
    except OSError:
        old = ""
    if not old.strip():
        old = HEADER
    elif not old.endswith("\n"):
        old += "\n"
    write_atomic(target, old + "\n".join(new) + "\n")
    return len(new)


def copy_from_handoff(root, handoff):
    """`add_from_note` for the handoff note file; never raises (the copy is a help, the wrap-up is what matters)."""
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read()
        rel = os.path.relpath(handoff, root).replace(os.sep, "/")
        return add_from_note(root, body, rel)
    except (OSError, ValueError):
        return 0
