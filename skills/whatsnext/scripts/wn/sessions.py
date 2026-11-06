"""Claude Code's session files: where a transcript lives and when its last turn was (ADR-0008)."""

import datetime
import glob
import json
import os
import re

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def claude_dir():
    """Claude Code's config folder: $CLAUDE_CONFIG_DIR, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def valid_session_id(value):
    return isinstance(value, str) and SESSION_ID_RE.match(value) is not None


def find_transcript(session_id, projects_dir=None):
    """The `<projects>/<folder>/<session_id>.jsonl` file, or None."""
    if not valid_session_id(session_id):
        return None
    folder = projects_dir or os.path.join(claude_dir(), "projects")
    hits = sorted(glob.glob(os.path.join(glob.escape(folder), "*", session_id + ".jsonl")))
    return hits[0] if hits else None


def entries(path):
    """Each JSON object of a transcript, skipping lines that do not parse."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                yield item


def transcript_cwd(path):
    """The first `cwd` the transcript records: the folder the session was started in."""
    for item in entries(path):
        cwd = item.get("cwd")
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def parse_time(text):
    """An ISO time such as `2026-10-25T18:15:54.713Z` as epoch seconds, or None."""
    if not isinstance(text, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return when.timestamp()


def prompt_text(item):
    """The text of a user prompt entry; None for a tool result, a meta entry or a non-user entry."""
    if item.get("type") != "user" or item.get("isMeta") or item.get("isSidechain"):
        return None
    content = (item.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return None


def last_turn_time(path, skip_prompt=None):
    """Epoch seconds of the last user or assistant entry. Bookkeeping lines (queue, system, attachment)
    are ignored: a resume appends them without any work. A turn that starts with the prompt `skip_prompt`
    (the wrap-up turn) is ignored too, so a handoff written in it is not older than the last turn."""
    last = None
    skipping = False
    for item in entries(path):
        text = prompt_text(item)
        if text is not None:
            skipping = skip_prompt is not None and text.strip() == skip_prompt
        if item.get("type") not in ("user", "assistant") or item.get("isSidechain") or skipping:
            continue
        when = parse_time(item.get("timestamp"))
        if when is not None and (last is None or when > last):
            last = when
    return last


TAIL_BYTES = 1000000  # how much of the transcript's end `latest_request` reads
NOT_A_REQUEST = ("<command-", "<local-command", "/compact", "<system-reminder", "<task-notification")


def tail_entries(path, size=TAIL_BYTES):
    """The JSON objects in the last `size` bytes of a transcript (a cut first line is dropped)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        f.seek(max(end - size, 0))
        raw = f.read()
    lines = raw.decode("utf-8", errors="replace").split("\n")
    if end > size:
        lines = lines[1:]
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            yield item


def latest_request(path, skip_prompt=None):
    """The text of the user's latest real request in a transcript, or None. Tool results, meta, sidechain and
    compact-summary entries, slash-command and injected entries, and the prompt `skip_prompt` are not requests."""
    found = None
    for item in tail_entries(path):
        if item.get("isCompactSummary"):
            continue
        text = prompt_text(item)
        if text is None:
            continue
        text = text.strip()
        if not text or text.startswith(NOT_A_REQUEST) or (skip_prompt is not None and text == skip_prompt):
            continue
        found = text
    return found
