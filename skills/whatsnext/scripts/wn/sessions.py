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


def request_text(item):
    """The user's own words in a prompt entry: each text block is checked on its own, and blocks that are
    slash-command or injected (NOT_A_REQUEST) are dropped before the rest are joined."""
    content = (item.get("message") or {}).get("content")
    blocks = [content] if isinstance(content, str) else \
        [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"] if isinstance(content, list) else []
    kept = [b.strip() for b in blocks if isinstance(b, str) and b.strip() and not b.strip().startswith(NOT_A_REQUEST)]
    return "\n".join(kept)


def latest_request(path, skip_prompt=None):
    """The text of the user's latest real request in a transcript, or None. Tool results, meta, sidechain and
    compact-summary entries, slash-command and injected entries, and the prompt `skip_prompt` are not requests."""
    found = None
    for item in tail_entries(path):
        if item.get("isCompactSummary"):
            continue
        if prompt_text(item) is None:
            continue
        text = request_text(item)
        if not text or (skip_prompt is not None and text == skip_prompt):
            continue
        found = text
    return found


AGENT_TOOLS = ("Agent", "Task")  # the subagent tool's name has changed between Claude Code versions


def open_work(path, max_agents=5):
    """What was still open at the end of a transcript, from its tail: {"agents": [(description, type, running)],
    "todo": [text]}. An agent is running while its tool_use has no tool_result; the todo is every task the
    agent marked `in_progress` with TodoWrite, or with TaskCreate and TaskUpdate (ids are 1, 2, 3 in order)."""
    agents, results, todo, tasks, created = {}, set(), [], {}, 0
    for item in tail_entries(path):
        if item.get("isSidechain"):
            continue
        content = (item.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result" and isinstance(block.get("tool_use_id"), str):
                results.add(block["tool_use_id"])
            if block.get("type") != "tool_use" or not isinstance(block.get("input"), dict):
                continue
            name, data = block.get("name"), block["input"]
            if name in AGENT_TOOLS:
                agents[block.get("id")] = (str(data.get("description") or data.get("subagent_type") or "agent"),
                                           str(data.get("subagent_type") or "agent"))
            elif name == "TodoWrite" and isinstance(data.get("todos"), list):
                todo = [str(t.get("content", "")) for t in data["todos"]
                        if isinstance(t, dict) and t.get("status") == "in_progress" and t.get("content")]
            elif name == "TaskCreate":
                created += 1
                tasks[str(created)] = [str(data.get("subject") or data.get("description") or ""), "pending"]
            elif name == "TaskUpdate" and str(data.get("taskId")) in tasks and isinstance(data.get("status"), str):
                tasks[str(data["taskId"])][1] = data["status"]
    if tasks:
        todo = [text for text, status in tasks.values() if status == "in_progress" and text]
    shown = [(d, t, i not in results) for i, (d, t) in agents.items()][-max_agents:]
    return {"agents": shown, "todo": todo}
