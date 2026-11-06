"""`whatsnext hook <event>`: the agents' hooks (ADR-0005).

Each agent's hook config calls this with the hook JSON on stdin. A hook must never
break a session: the caller (whatsnext.py) turns any error into silence and exit 0,
and nothing here prints except the session-start note. Outside a whatsnext project
every event does nothing.

- session-start: print the resume note.
- plan-shown / plan-approved: Claude Code PreToolUse / PostToolUse on ExitPlanMode.
- prompt-submit: Claude Code; a plan still `shown` when the mode is no longer `plan`
  was used without approval (ADR-0006). The exact prompt `wrap up`
  prints the instructions that write the handoff note (ADR-0008).
- stop: Codex reads its plan from `transcript_path` (item 5).
- stop: also records a wrap-up that was requested in this session and wrote the handoff (ADR-0008).
- pre-compact: Claude Code prints plain text (the compact instructions, capped; P-20); every agent records a compact with no fresh handoff (P-4).
- stop / pre-compact / session-end: also write the facts (journal line and progress header, ADR-0005).
"""

import argparse
import contextlib
import io
import json
import os

from . import capture as gwcapture
from . import config as gwconfig
from . import journal as gwjournal
from . import packet as gwpacket
from . import redact as gwredact
from . import sessions as gwsessions
from . import status as gwstatus
from . import wrapup as gwwrapup

EVENTS = ("session-start", "plan-shown", "plan-approved", "prompt-submit", "stop", "pre-compact", "session-end")
PRECOMPACT_CAP = 3000  # characters printed at PreCompact (P-20)
REQUEST_CAP = 2000  # characters of the user's latest request kept verbatim (P-6)
FACT_EVENTS = ("stop", "pre-compact", "session-end")  # these write the facts layer
AGENTS = ("claude-code", "codex")


def is_project(root, effective):
    """The project gate: the progress module is on and the folder is a whatsnext project (`.whatsnext/` or the entry file)."""
    return bool(effective.module_on("progress") and gwpacket.is_project(root, effective))


def project(data):
    """(root, effective) of the hook's folder, or None outside a whatsnext project."""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and os.path.isdir(data["cwd"]) else None
    root = gwconfig.find_root(cwd)
    effective = gwconfig.load(root)
    if not is_project(root, effective):
        return None
    return root, effective


def branch_task(root, effective):
    """The active task recorded on the current branch, or None (no fallback; see status.branch_task)."""
    return gwstatus.branch_task(gwstatus.load_tasks(root, gwstatus.status_folder(root, effective)),
                                gwstatus.current_branch(root))


def capture(root, effective, status, agent, text=None):
    """`progress capture` on this branch's active task, silently. Its exit code does not matter to a hook.
    No active task on this branch: nothing is written (another branch's item is never touched)."""
    task = branch_task(root, effective)
    if task is None:
        return 0
    args = argparse.Namespace(task_id=task.id, status=status, agent=agent, file=None, text=text)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return gwcapture.run(root, gwstatus.status_folder(root, effective), effective, args)


def plan_status(root, effective):
    """This branch's active task's captured plan status text, or None."""
    task = branch_task(root, effective)
    return gwcapture.plan_field(task)[1] if task else None


# ---- Codex: the plan in the session file -----------------------------------


def codex_plan(path, turn_id):
    """("shown", text) when this turn has a Plan item; ("approved", None) when this turn started in
    `default` mode and the turns before it, back to the last turn with a Plan item, were all `plan`
    mode (a plan-mode turn with no new plan, such as a typed "approve", does not break the chain).
    Else None. An unknown format gives None."""
    turns, plans = [], {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") if isinstance(record, dict) else None
            if record.get("type") != "event_msg" or not isinstance(payload, dict):
                continue
            if payload.get("type") == "task_started" and isinstance(payload.get("turn_id"), str):
                turns.append((payload["turn_id"], payload.get("collaboration_mode_kind")))
            elif payload.get("type") == "item_completed":
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") == "Plan" and isinstance(item.get("text"), str):
                    plans[payload.get("turn_id")] = item["text"]
    if turn_id in plans:
        return "shown", plans[turn_id]
    ids = [t for t, _mode in turns]
    if turn_id in ids:
        i = ids.index(turn_id)
        if turns[i][1] == "default":
            for prev_id, prev_mode in reversed(turns[:i]):
                if prev_id in plans:
                    return "approved", None
                if prev_mode != "plan":
                    break
    return None


def codex_stop(root, effective, data):
    path, turn_id = data.get("transcript_path"), data.get("turn_id")
    if not isinstance(path, str) or not isinstance(turn_id, str) or not os.path.isfile(path):
        return
    found = codex_plan(path, turn_id)
    if found:
        capture(root, effective, found[0], "codex", found[1])


# ---- events ----------------------------------------------------------------


def command_line():
    """The line that tells an agent with no plugin folder how to run whatsnext (Codex)."""
    script = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "whatsnext.py"))
    return ('whatsnext command: WHATSNEXT_AGENT=codex python3 "%s" <command>. Run `plan start <id>` and `plan done <id> --verify "<cmd>"` '
            "with it, and start the item before you create files; do not tick PLAN.md by hand." % script)


def session_start(root, effective, data, agent=None):
    result = gwpacket.build(root, effective, compacted=(data.get("source") == "compact"),
                            session_id=data.get("session_id"))
    text = result["text"] if result else None
    if not text:
        return ""
    if agent == "codex":  # Codex has no plugin folder to resolve `whatsnext` against; the note is not committed
        text += "\n" + command_line()
    return text + "\n"


def latest_request(transcript, facts):
    """The "Keep verbatim" block for the user's latest request, or "". It is redacted, clipped to REQUEST_CAP
    characters, and short enough that it and the facts block fit the PreCompact cap. Any error gives ""."""
    if not transcript or not os.path.isfile(transcript):
        return ""
    try:
        text = gwsessions.latest_request(transcript, gwwrapup.PROMPT)
    except (OSError, ValueError):
        return ""
    if not text:
        return ""
    head = "Keep verbatim (the user's latest request):\n"
    room = min(REQUEST_CAP, PRECOMPACT_CAP - len(facts) - len(head) - 4)
    return head + gwwrapup.clip_to(gwredact.mask_secrets(text), room) if room > 0 else ""


def precompact(root, effective, data, agent=None):
    """PreCompact (P-4, P-20, P-26). Records "compacted without wrap-up" when this session has no fresh handoff
    note (the resume note shows it after the compact). Claude Code: returns plain text, at most PRECOMPACT_CAP
    characters: the compact instructions and a facts block, or the facts block alone when the user typed
    `/compact <text>`. Codex ignores PreCompact output, so it gets no text."""
    task = branch_task(root, effective)
    if task is None:  # no active task on this branch: nothing to carry, nothing written
        return ""
    session_id = data.get("session_id") if isinstance(data.get("session_id"), str) else None
    transcript = data.get("transcript_path") if isinstance(data.get("transcript_path"), str) else None
    state = gwwrapup.handoff_state(gwwrapup.handoff_path(root, effective), transcript, session_id, root)
    when = gwstatus.stamp_time() if state["stale"] else None
    gwwrapup.mark_compacted(root, session_id, when)
    if agent == "codex":
        return ""
    from . import compact as gwcompact  # imported here: compact imports this module
    lines = ["whatsnext facts:", gwcompact.facts_text(root, effective, task)]
    if when:
        lines.append("Compacted without wrap-up at %s." % when)
    facts = " ".join(lines)
    request = latest_request(transcript, facts)
    custom = data.get("custom_instructions")
    if isinstance(custom, str) and custom.strip():  # the user wrote their own compact text: add only the facts
        return gwwrapup.clip_to(request + "\n\n" + facts if request else facts, PRECOMPACT_CAP) + "\n"
    tail = (request + "\n\n" if request else "") + facts
    room = PRECOMPACT_CAP - len(tail) - 2
    body = gwwrapup.clip_to(gwwrapup.compact_instructions(root, effective, session_id).strip(), max(room, 0))
    return (body + "\n\n" if body else "") + gwwrapup.clip_to(tail, PRECOMPACT_CAP) + "\n"


def handle(event, data, agent=None):
    """The text to print for one event ("" for nothing)."""
    if not isinstance(data, dict):
        return ""
    found = project(data)
    if found is None:
        return ""
    root, effective = found
    out = ""
    if event == "session-start":
        return session_start(root, effective, data, agent)
    if event == "plan-shown":
        tool_input = data.get("tool_input")
        text = tool_input.get("plan") if isinstance(tool_input, dict) else None
        if isinstance(text, str) and text.strip():
            capture(root, effective, "shown", agent or "claude-code", text)
    elif event == "plan-approved":
        capture(root, effective, "approved", agent or "claude-code")
    elif event == "prompt-submit":
        mode = data.get("permission_mode")
        if agent != "codex" and isinstance(mode, str) and mode != "plan" and \
                plan_status(root, effective) == gwcapture.STATUS_TEXT["shown"]:
            capture(root, effective, "unapproved", agent or "claude-code")
        prompt = data.get("prompt")
        if isinstance(prompt, str) and prompt.strip() == gwwrapup.PROMPT:
            return gwwrapup.begin(root, effective, data)
    elif event == "pre-compact":
        try:
            out = precompact(root, effective, data, agent)
        except Exception:  # PreCompact output is a help, never a failure
            out = ""
    elif event == "stop":
        if agent == "codex":
            codex_stop(root, effective, data)
        try:
            gwwrapup.settle(root, effective, data, agent)
        except Exception:  # recording a wrap-up must never break the agent's session
            pass
    if event in FACT_EVENTS:
        try:
            gwjournal.record(root, effective, event, data)
        except Exception:  # the facts must never break the agent's session (the caller hides stderr anyway)
            pass
    return out


def read_input(stream):
    """The hook JSON: {} when empty, None when it is not a JSON object."""
    raw = stream.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
