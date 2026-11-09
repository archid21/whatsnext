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
- pre-edit: Claude Code and Codex PreToolUse on Edit, Write and apply_patch; warns or denies a hand-ticked plan item (P-7).
- permission: PermissionRequest; allows writing the handoff note while this session's `wrap up` is open (P-43).
- idle-offer: asked by the hooks module before it shows the opt-in tip; prints `{"offer": true|false}` (P-42).
- idle-check: asked by the hooks module 45 minutes after the last turn; prints `{"fire": true|false}` (ADR-0016, P-40).
- post-compact: Claude Code's PostCompact; keeps `compact_summary` in git-ignored session state (P-21).
- stop / pre-compact / session-end: also write the facts (journal line and progress header, ADR-0005).
"""

import argparse
import contextlib
import io
import json
import os
import re

from . import capture as gwcapture
from . import config as gwconfig
from . import idle as gwidle
from . import journal as gwjournal
from . import packet as gwpacket
from . import redact as gwredact
from . import sessions as gwsessions
from . import status as gwstatus
from . import util as gwutil
from . import welcome as gwwelcome
from . import wrapup as gwwrapup

EVENTS = ("session-start", "plan-shown", "plan-approved", "prompt-submit", "stop", "pre-compact", "post-compact",
          "pre-edit", "session-end", "interrupt", "idle-check", "idle-offer", "permission")
PRECOMPACT_CAP = 3000  # characters printed at PreCompact (P-20)
CARRY_REQUEST_CAP = 250  # characters of the latest request repeated in the resume note after a compact (ADR-0015)
CARRY_WORK_CAP = 150  # characters of the subagents and todo line repeated there
OPEN_WORK_CAP = 500  # characters for the subagents and todo line (P-25)
REQUEST_CAP = 2000  # characters of the user's latest request kept verbatim (P-6)
FACT_EVENTS = ("stop", "pre-compact", "session-end", "interrupt")  # these write the facts layer
AGENTS = ("claude-code", "codex")
# Events that leave runtime evidence (`health-<agent>-<event>.json`) for `whatsnext doctor`. The frequent events
# (pre-edit, permission, plan-shown, idle-check, ...) write nothing, so a hook stays quiet on disk.
OBSERVED_EVENTS = ("session-start", "prompt-submit", "stop", "pre-compact", "session-end", "interrupt")


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
            if not isinstance(record, dict) or record.get("type") != "event_msg" or not isinstance(payload, dict):
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


def codex_format_known(path):
    """A turn-start record alone does not demonstrate that plans are readable."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") if isinstance(record, dict) else None
            if isinstance(payload, dict) and record.get("type") == "event_msg" and payload.get("type") == "item_completed":
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") == "Plan" and isinstance(item.get("text"), str):
                    return True
    return False


UNREADABLE = "capture.unreadable"


def unreadable_path(root):
    return os.path.join(root, gwjournal.SESSIONS_DIR, UNREADABLE + ".json")


def note_capture_health(root, ok, reason=None):
    """P-19: one `capture.unreadable` fact while Codex's plan cannot be read; removed when it can. `doctor` shows it.
    The first reason and time are kept; later turns add to `count`."""
    path = unreadable_path(root)
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)):  # never write or remove through a link
        return
    if ok:
        if os.path.isfile(path):
            os.remove(path)
        return
    state = {"fact": UNREADABLE, "reason": reason, "since": gwstatus.stamp_time(), "count": 0}
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        if isinstance(old, dict) and old.get("fact") == UNREADABLE:
            state = old
    except (OSError, ValueError):
        pass
    state["count"] = int(state.get("count") or 0) + 1
    gwutil.write_atomic(path, json.dumps(state, indent=2) + "\n", newline=None)


def codex_stop(root, effective, data):
    path, turn_id = data.get("transcript_path"), data.get("turn_id")
    if not isinstance(path, str) or not isinstance(turn_id, str):
        observe(root, "codex", "plan-capture", "unverified", "Stop supplied no transcript path or turn id")
        return
    try:
        found = codex_plan(path, turn_id)
        known = True if found else codex_format_known(path)
    except OSError as e:
        observe(root, "codex", "plan-capture", "unverified", "Cannot read the transcript")
        note_capture_health(root, False, "cannot read the transcript (%s)" % (e.strerror or "error"))
        return
    if found:
        result = capture(root, effective, found[0], "codex", found[1])
        if branch_task(root, effective) is not None and result == 0:
            observe(root, "codex", "plan-capture", "observed", "captured " + found[0])
    if known:
        note_capture_health(root, True)
    else:
        observe(root, "codex", "plan-capture", "unverified", "No readable Plan item observed")
        started = any(r.get("type") == "event_msg" and isinstance(r.get("payload"), dict)
                      and r["payload"].get("type") == "task_started" for r in gwsessions.entries(path))
        if not started:
            note_capture_health(root, False, "the transcript has no task_started records (format changed?)")


# ---- events ----------------------------------------------------------------


def command_line():
    """The line that tells an agent with no plugin folder how to run whatsnext (Codex)."""
    script = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "whatsnext.py"))
    return ('whatsnext command: WHATSNEXT_AGENT=codex python3 "%s" <command>. Run `plan start <id>` and `plan done <id> --verify "<cmd>"` '
            "with it, and start the item before you create files; do not tick PLAN.md by hand." % script)


def session_start(root, effective, data, agent=None):
    try:  # old sessions' state files (ADR-0018); a failed prune never stops the resume note
        gwjournal.prune_sessions(root, keep_session=data.get("session_id"))
    except Exception:
        pass
    if data.get("source") == "compact":
        gwwrapup.take_resume_marker(root, data.get("session_id"))  # SessionStart said it: the prompt need not
    result = gwpacket.build(root, effective, compacted=(data.get("source") == "compact"),
                            session_id=data.get("session_id"))
    text = result["text"] if result else None
    if not text:
        return ""
    if agent == "codex":  # Codex has no plugin folder to resolve `whatsnext` against; the note is not committed
        text += "\n" + command_line()
        return text + "\n"
    return claude_session_start(text, result)


NEXT_LINE_RE = re.compile(r"^Next[^:\n]*:\s*(.+)$", re.M)
BANNER_NEXT_CAP = 110


def claude_session_start(text, result):
    """Claude Code gets JSON: the note as `additionalContext` (the model reads it) and a one-line `systemMessage`
    (P-41), because plain stdout is shown to nobody until the model answers."""
    found = NEXT_LINE_RE.search(text)
    if found:
        banner = "whatsnext: resume note loaded. Next: %s Type `what's next?` for details." % \
                 gwwrapup.clip_to(" ".join(found.group(1).split()), BANNER_NEXT_CAP)
    else:
        banner = "whatsnext: resume note loaded. Type `what's next?` to see where you left off."
    out = {"systemMessage": banner, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    return json.dumps(out) + "\n"


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


def open_work_text(transcript):
    """One short line naming the subagents launched this session and the agent's in-progress todo, or "".
    Plain facts from the transcript tail; any error gives ""."""
    if not transcript or not os.path.isfile(transcript):
        return ""
    try:
        work = gwsessions.open_work(transcript)
    except (OSError, ValueError):
        return ""
    parts = []
    if work["agents"]:
        parts.append("Subagents launched: " + "; ".join("%s (%s, %s)" % (
            gwwrapup.clip_to(" ".join(d.split()), 60), gwwrapup.clip_to(t, 30), "status unknown" if running is None else "running" if running else "finished")
            for d, t, running in work["agents"]) + ".")
    if work["todo"]:
        parts.append("In-progress todo: " + "; ".join(gwwrapup.clip_to(" ".join(t.split()), 80) for t in work["todo"][:3]) + ".")
    return gwwrapup.clip_to(gwredact.mask_secrets(" ".join(parts)), OPEN_WORK_CAP) if parts else ""


def carry_text(transcript):
    """What the resume note repeats after the compact (ADR-0015): the user's latest request and the open work,
    redacted and clipped (at most about 420 characters), or None. Any error gives None."""
    if not transcript or not os.path.isfile(transcript):
        return None
    try:
        request = gwsessions.latest_request(transcript, gwwrapup.PROMPT)
        work = open_work_text(transcript)
    except Exception:
        return None
    parts = []
    if request:
        flat = " ".join(gwredact.mask_secrets(request).split())
        parts.append('Before the compact the user asked: "%s"' % gwwrapup.clip_to(flat, CARRY_REQUEST_CAP))
    if work:
        parts.append(gwwrapup.clip_to(work, CARRY_WORK_CAP))
    return " ".join(parts) or None


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
    carry = carry_text(transcript) if effective.get("note.carryAfterCompact") else None
    gwwrapup.mark_compacted(root, session_id, when, carry)
    if agent == "codex":
        gwwrapup.set_resume_marker(root, session_id)  # Codex may not pass source=compact; the next prompt shows the note
        return ""
    from . import compact as gwcompact  # imported here: compact imports this module
    lines = ["whatsnext facts:", gwcompact.facts_text(root, effective, task)]
    if when:
        lines.append("Compacted without wrap-up at %s." % when)
    open_work = open_work_text(transcript)
    if open_work:
        lines.append(open_work)
    facts = " ".join(lines)
    request = latest_request(transcript, facts)
    custom = data.get("custom_instructions")
    if isinstance(custom, str) and custom.strip():  # the user wrote their own compact text: add only the facts
        return gwwrapup.clip_to(request + "\n\n" + facts if request else facts, PRECOMPACT_CAP) + "\n"
    tail = (request + "\n\n" if request else "") + facts
    room = PRECOMPACT_CAP - len(tail) - 3  # the blank line (2) and the final newline (1)
    body = gwwrapup.clip_to(gwwrapup.compact_instructions(root, effective, session_id).strip(), max(room, 0))
    return (body + "\n\n" if body else "") + gwwrapup.clip_to(tail, PRECOMPACT_CAP) + "\n"


TICK_OLD_RE = re.compile(r"^\s*- \[ \] (P-\d+)\b", re.MULTILINE)
TICK_NEW_RE = re.compile(r"^\s*- \[[xX]\] (P-\d+)\b", re.MULTILINE)
PATCH_OLD_RE = re.compile(r"^-\s*- \[ \] (P-\d+)\b", re.MULTILINE)
PATCH_NEW_RE = re.compile(r"^\+\s*- \[[xX]\] (P-\d+)\b", re.MULTILINE)


def ticked_ids(root, effective, data):
    """The plan item ids an Edit, Write, MultiEdit or Codex `apply_patch` call turns from `- [ ]` into `- [x]` in the
    plan file, sorted. [] when the call is not about the plan file or ticks nothing."""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    plan_rel = effective.get("paths.plan")
    plan_path = os.path.realpath(os.path.join(root, plan_rel))
    patch = tool_input.get("command") if data.get("tool_name") == "apply_patch" else None
    if isinstance(patch, str):  # Codex: `*** Update File: <path>` then `-- [ ] P-1` / `+- [x] P-1` lines
        if plan_rel not in patch and os.path.basename(plan_rel) not in patch:
            return []
        return sorted(set(PATCH_OLD_RE.findall(patch)) & set(PATCH_NEW_RE.findall(patch)))
    target = tool_input.get("file_path")
    if not isinstance(target, str) or os.path.realpath(os.path.join(root, target)) != plan_path:
        return []
    ids = set()
    if isinstance(tool_input.get("content"), str):  # Write: compare with the file as it is now
        try:
            with open(plan_path, encoding="utf-8", errors="replace") as f:
                before = set(TICK_OLD_RE.findall(f.read()))
        except OSError:
            before = set()
        ids = before & set(TICK_NEW_RE.findall(tool_input["content"]))
    edits = tool_input.get("edits") if isinstance(tool_input.get("edits"), list) else [tool_input]
    for edit in edits:
        if isinstance(edit, dict) and isinstance(edit.get("old_string"), str) and isinstance(edit.get("new_string"), str):
            ids |= set(TICK_OLD_RE.findall(edit["old_string"])) & set(TICK_NEW_RE.findall(edit["new_string"]))
    return sorted(ids)


def plan_tick_guard(root, effective, data):
    """PreToolUse (P-7): JSON for the agent when it ticks a plan item by hand, else "". `plan.tickGuard` picks warn
    (the default), off or deny. Claude Code reads `additionalContext` and `permissionDecision` from this shape; Codex's
    PreToolUse takes the same `permissionDecision` (docs only: not run against Codex)."""
    mode = effective.get("plan.tickGuard")
    if mode == "off" or not effective.module_on("plan"):
        return ""
    ids = ticked_ids(root, effective, data)
    if not ids:
        return ""
    first = ids[0]
    message = ("whatsnext: %s is being ticked in PLAN.md by hand. Use `plan done %s --verify \"<command>\"` instead, so a "
               "passing command is the proof (ADR-0003)." % (", ".join(ids), first))
    if mode == "deny":
        out = {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": message}
    else:
        out = {"hookEventName": "PreToolUse", "additionalContext": message}
    return json.dumps({"hookSpecificOutput": out}) + "\n"


def with_welcome(out, welcome, agent):
    """`out` (a session-start answer) with the first-run welcome in front of it. Claude Code shows the welcome as the
    `systemMessage`; Codex prints plain text."""
    if not welcome:
        return out
    if agent == "codex":
        return welcome + "\n" + out
    try:
        payload = json.loads(out) if out.strip() else {}
    except ValueError:
        return out
    banner = payload.get("systemMessage")
    payload["systemMessage"] = welcome + ("\n" + banner if banner else "")
    return json.dumps(payload) + "\n"


def observe(root, agent, event, status="observed", detail=None):
    """Per-agent, per-event evidence. This reports execution, not hook trust or end-to-end success."""
    if agent not in AGENTS:
        return
    path = os.path.join(root, gwjournal.SESSIONS_DIR, "health-%s-%s.json" % (agent, event))
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)):
        return
    state = {"agent": agent, "event": event, "status": status, "time": gwstatus.stamp_time(), "detail": detail}
    gwutil.write_atomic(path, json.dumps(state) + "\n", newline=None)


def handle(event, data, agent=None):
    result = handle_event(event, data, agent)
    found = project(data) if event in OBSERVED_EVENTS and isinstance(data, dict) else None
    if found:
        try:
            observe(found[0], agent or "claude-code", event)
        except OSError:
            pass
    return result


def handle_event(event, data, agent=None):
    """The text to print for one event ("" for nothing)."""
    if not isinstance(data, dict):
        return ""
    welcome = ""
    if event == "session-start":
        try:  # the first-run welcome (P-44): once per install, in any folder
            welcome = gwwelcome.take_first_run(data)
        except Exception:  # a welcome must never break the session
            welcome = ""
    found = project(data)
    if found is None:
        return with_welcome("", welcome, agent)
    root, effective = found
    out = ""
    if event == "session-start":
        return with_welcome(session_start(root, effective, data, agent), welcome, agent)
    if event == "plan-shown":
        tool_input = data.get("tool_input")
        text = tool_input.get("plan") if isinstance(tool_input, dict) else None
        if isinstance(text, str) and text.strip():
            capture(root, effective, "shown", agent or "claude-code", text)
    elif event == "plan-approved":
        capture(root, effective, "approved", agent or "claude-code")
    elif event == "prompt-submit":
        prompt = data.get("prompt")
        if isinstance(prompt, str) and prompt.strip() == gwwrapup.PROMPT:
            resume = ""
            if agent == "codex" and gwwrapup.take_resume_marker(root, data.get("session_id")):
                resume = session_start(root, effective, dict(data, source="compact"), agent)
            return resume + gwwrapup.begin(root, effective, data, agent)
        if agent == "codex":  # Codex: only the once-after-compact resume note (P-22)
            if gwwrapup.take_resume_marker(root, data.get("session_id")):
                return session_start(root, effective, dict(data, source="compact"), agent)
            return ""
        mode = data.get("permission_mode")
        if agent != "codex" and isinstance(mode, str) and mode != "plan" and \
                plan_status(root, effective) == gwcapture.STATUS_TEXT["shown"]:
            capture(root, effective, "unapproved", agent or "claude-code")
    elif event == "pre-compact":
        try:
            out = precompact(root, effective, data, agent)
        except Exception:  # PreCompact output is a help, never a failure
            out = ""
    elif event == "idle-offer":
        try:
            out = gwidle.offer_text(root, effective, data)
        except Exception:  # no answer reads as "do not offer"
            out = ""
    elif event == "idle-check":
        try:
            out = gwidle.check_text(root, effective, data)
        except Exception:  # no answer reads as "do not fire"
            out = ""
    elif event == "permission":
        try:
            out = gwwrapup.allow_handoff_write(root, effective, data)
        except Exception:  # no answer leaves the prompt to the person
            out = ""
    elif event == "pre-edit":
        try:
            out = plan_tick_guard(root, effective, data)
        except Exception:  # a guard must never break an edit
            out = ""
    elif event == "post-compact":
        try:  # keep the summary and say how much of the plan it kept (P-21); never break the session
            gwwrapup.save_summary(root, data.get("session_id"), data.get("compact_summary"), branch_task(root, effective))
        except Exception:
            pass
    elif event == "stop":
        if agent == "codex":
            codex_stop(root, effective, data)
        try:
            if gwwrapup.settle(root, effective, data, agent):
                observe(root, agent or "claude-code", "handoff", "observed", "handoff recorded at Stop")
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
