"""P-68: the Files, Links and Skills sections of the handoff note, from the session's own tool calls.

At Stop, after the agent wrote the note in a `wrap up`, whatsnext reads the session's transcript and adds three
sections the agent does not write: the files it read and created in the repository, the links it opened and the
skills it used. Nothing here calls a model. The transcript is data: every value is cleaned before it is written,
paths outside the repository are left out (the note is committed and shared), and query strings and fragments are
removed from links because they can carry tokens.
"""

import os
import re
from urllib.parse import urlsplit, urlunsplit

from . import redact as gwredact
from . import sessions as gwsessions

SECTIONS = ("Files", "Links", "Skills")
MAX_ENTRIES = 10
MAX_VALUE = 160  # one path, link or skill name
READ_TOOLS = ("Read",)
WRITE_TOOLS = ("Write",)
EDIT_TOOLS = ("Edit", "MultiEdit", "NotebookEdit")
LINK_TOOLS = ("WebFetch",)
LINK_SUFFIXES = ("__navigate", "__preview_start")  # the browser tools: mcp__<server>__navigate and the like
SKILL_TOOLS = ("Skill",)
CODEX_SKILL_RE = re.compile(r"([A-Za-z0-9._-]+)[/\\]SKILL\.md\b")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def clean(value):
    """One value, single line, secrets masked, cut to MAX_VALUE; '' when nothing is left."""
    if not isinstance(value, str):
        return ""
    text = gwredact.mask_secrets(CONTROL_RE.sub("", value).strip())
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE - 1].rstrip() + "…"


def repo_path(root, path, cwd=None):
    """`path` relative to `root`, with `/`, or None when it is outside the repository."""
    if not isinstance(path, str) or not path.strip():
        return None
    full = path if os.path.isabs(path) else os.path.join(cwd or root, path)
    real, top = os.path.realpath(full), os.path.realpath(root)
    try:
        if os.path.commonpath([real, top]) != top or real == top:
            return None
    except ValueError:  # another drive
        return None
    rel = os.path.relpath(real, top).replace(os.sep, "/")
    return None if rel == ".git" or rel.startswith(".git/") else rel


def plain_link(url):
    """`url` without its query string, fragment or user name and password; '' for anything not http(s)."""
    if not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname or ""
        port = ":%d" % parts.port if parts.port else ""
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not host:
        return ""
    return clean(urlunsplit((parts.scheme, host + port, parts.path, "", "")))


def add(seen, values, value):
    if value and value not in seen:
        seen.add(value)
        values.append(value)


def collect(path, root, since=None):
    """{"read", "created", "links", "skills"} from the transcript at `path`, in first-use order. `since` (epoch
    seconds) leaves out older entries. A file counts as created when the session wrote it before reading or editing it (Claude Code refuses to
    overwrite a file it has not read). Subagent entries are left out: their work reaches the note through
    the main session."""
    read, created, links, skills = [], [], [], []
    seen_read, seen_created, seen_links, seen_skills = set(), set(), set(), set()
    touched, changed = set(), set()
    cwd = gwsessions.transcript_cwd(path)
    for item in gwsessions.entries(path):
        if item.get("isSidechain"):
            continue
        when = gwsessions.parse_time(item.get("timestamp"))
        if since is not None and (when is None or when < since):
            continue
        payload = item.get("payload")
        if item.get("type") == "response_item" and isinstance(payload, dict) and payload.get("type") == "function_call":
            # Codex loads a skill by reading its SKILL.md
            for m in CODEX_SKILL_RE.finditer(str(payload.get("arguments", ""))):
                add(seen_skills, skills, clean(m.group(1)))
            continue
        content = (item.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use" or not isinstance(block.get("input"), dict):
                continue
            name, data = str(block.get("name") or ""), block["input"]
            if name in READ_TOOLS + WRITE_TOOLS + EDIT_TOOLS:
                rel = repo_path(root, data.get("file_path") or data.get("notebook_path"), cwd)
                if rel is None:
                    continue
                if name in READ_TOOLS:
                    add(seen_read, read, clean(rel))
                elif name in WRITE_TOOLS and rel not in touched:
                    add(seen_created, created, clean(rel))
                if name not in READ_TOOLS:
                    changed.add(clean(rel))
                touched.add(rel)
            elif name in LINK_TOOLS or name.endswith(LINK_SUFFIXES):
                add(seen_links, links, plain_link(data.get("url")))
            elif name in SKILL_TOOLS:
                add(seen_skills, skills, clean(data.get("skill")))
    # a file read and then changed is in What changed; Files lists what was only read
    return {"read": [r for r in read if r not in changed], "created": created, "links": links, "skills": skills}


def is_skipped(rel, skip):
    return any(rel == s or (s.endswith("/") and rel.startswith(s)) for s in skip)


def sections_text(facts, limit=MAX_ENTRIES):
    """The three sections as Markdown, each list cut to `limit` entries; '' when every list is empty."""
    def cut(values):
        shown = values[:limit]
        if len(values) > limit:
            shown = shown + ["and %d more" % (len(values) - limit)]
        return ", ".join(shown)

    parts = []
    files = []
    if facts.get("read") and limit:
        files.append("- Read: " + cut(facts["read"]))
    if facts.get("created") and limit:
        files.append("- Created: " + cut(facts["created"]))
    if files:
        parts.append("## Files\n\n" + "\n".join(files))
    if facts.get("links") and limit:
        shown = ["- " + v for v in facts["links"][:limit]]
        if len(facts["links"]) > limit:
            shown.append("- and %d more" % (len(facts["links"]) - limit))
        parts.append("## Links\n\n" + "\n".join(shown))
    if facts.get("skills") and limit:
        parts.append("## Skills\n\n" + cut(facts["skills"]))
    return "\n\n".join(parts)


def strip_sections(body):
    """`body` without any Files, Links or Skills section (the agent's own, or an earlier run's)."""
    out, dropping = [], False
    for line in body.split("\n"):
        m = re.match(r"^##(?!#)\s+(.*?)\s*#*\s*$", line)
        if m:
            dropping = m.group(1).strip().lower() in [s.lower() for s in SECTIONS]
        if not dropping:
            out.append(line)
    return "\n".join(out).rstrip()


def add_to_note(body, facts, max_chars):
    """`body` with the sections added at the end, as many entries as fit in `max_chars` (never fewer than one
    per list when any fit). The agent's text is never cut: when nothing fits, the note is returned unchanged
    apart from the removal of old sections."""
    base = strip_sections(body)
    for limit in range(MAX_ENTRIES, 0, -1):
        extra = sections_text(facts, limit)
        if not extra:
            break
        text = base + "\n\n" + extra + "\n"
        if len(text) <= max_chars:
            return text
    return base + "\n"


def write_sections(root, handoff, transcript, since=None, skip=(), max_chars=3000):
    """Add the sections to the handoff note at `handoff` from `transcript`. Returns the facts, or None when the
    transcript cannot be read. A note that is already too long is left as it is."""
    if not (isinstance(transcript, str) and os.path.isfile(transcript)):
        return None
    try:
        facts = collect(transcript, root, since)
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except (OSError, ValueError):
        return None
    facts = {k: [v for v in vals if not is_skipped(v, skip)] if k in ("read", "created") else vals
             for k, vals in facts.items()}
    text = add_to_note(body, facts, max_chars)
    if text != body:
        from .util import write_atomic
        write_atomic(handoff, text)
    return facts
