"""Wrap up (ADR-0008) and the compact instructions (ADR-0009) built from the handoff.

- `begin` runs when the user's prompt is exactly `wrap up` (the UserPromptSubmit hook). It prints the
  instructions that tell the agent to write the handoff note, and remembers the request.
- `settle` runs at Stop. When the handoff file was written since the request, it records the
  `session.wrapup` event (backend) and one `wrap-up` journal line.
- `compact_instructions` is the text that follows `/compact ` in an open session.
- The note starts with `Session:`, `Task:` and `Written:` lines (ADR-0008). `settle` also writes a
  sidecar, `.whatsnext/sessions/<session>.handoff.json`, with the file's SHA-256. A note is fresh for a session
  only when that session's sidecar matches the file; any other note is foreign.
- `compact_line` renders the one-line `/compact <text>` from a written note, with a cap per section.
"""

import datetime
import hashlib
import json
import os
import re
import sys

from . import backend as gwbackend
from . import claims as gwclaims
from . import config as gwconfig
from . import journal as gwjournal
from . import sessions as gwsessions
from . import status as gwstatus
from .util import now_utc, write_atomic

PROMPT = "wrap up"
DEFAULT_HANDOFF = "docs/project/HANDOFF.md"
TIMEZONE = "America/Los_Angeles"
MAX_HANDOFF_CHARS = 3000
MAX_NEXT_CHARS = 400
MAX_LINE_CHARS = 1800  # the one-line `/compact <text>` the agent ends its wrap-up reply with
# (label in the line, section names in the note, cap in characters). Next and Constraints are never cut to make
# the line fit; Blockers, Decisions and Goal give way first, in that order.
LINE_SECTIONS = (
    ("Goal", ("Goal",), 200),
    ("Next", ("Next action",), MAX_NEXT_CHARS),
    ("Constraints", ("Constraints",), 600),
    ("Decisions", ("Decisions",), 400),
    ("Dead ends", ("Dead ends",), 300),
    ("Blockers", ("Open questions and blockers", "Open questions"), 300),
)
LINE_SHRINK = ("Dead ends", "Blockers", "Decisions", "Goal")
LINE_MIN_SLOT = 20
BODY_ORDER = ("Next action", "Constraints", "Goal", "Decisions", "Dead ends", "Open questions and blockers",
              "Open questions", "State", "What changed")
HEADER_LINES = 12
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "whatsnext.py")
# A line in AGENTS.md such as `Handoff: docs/handoff.md` or `- Handoff file: `notes/HANDOFF.md``.
AGENTS_RE = re.compile(r"^[\s>*-]*handoff(?:\s+(?:file|note))?\s*:\s*`?([^\s`]+)`?\s*$", re.I | re.M)

LINE_BASE = ("Keep: the task goal, the decisions and why, the constraints, the file paths and commands that matter, "
             "and the next steps. Drop: tool output and file dumps. Keep dead ends (approaches tried and dropped) with the reason.")

COMPACT_BASE = (
    "Keep: the current task and its goal, the decisions made and why, the open questions, the file paths and "
    "commands that matter, and the next steps. Drop: tool output and file dumps. Keep dead ends (approaches tried "
    "and abandoned) with the reason each failed, so they are not tried again."
)


# ---- the handoff file ------------------------------------------------------


def handoff_path(root, effective):
    """Absolute path of the handoff note. A `paths.handoff` setting wins; else the path AGENTS.md names; else the default."""
    if effective.source("paths.handoff")[0] == "default":
        try:
            with open(os.path.join(root, "AGENTS.md"), encoding="utf-8", errors="replace") as f:
                named = AGENTS_RE.search(f.read())
        except OSError:
            named = None
        if named and gwconfig.is_relative_path(named.group(1)):
            return os.path.join(root, *named.group(1).split("/"))
    return os.path.join(root, *effective.get("paths.handoff").split("/"))


def pacific_now(now=None):
    """(`Wed 2026-11-04 9:03 PM PST`, `2026-11-05T05:03Z`): the time to write in the handoff, Pacific and UTC."""
    now = now or now_utc()
    utc = now.strftime("%Y-%m-%dT%H:%MZ")
    try:
        import zoneinfo

        local = now.astimezone(zoneinfo.ZoneInfo(TIMEZONE))
    except Exception:  # no zoneinfo or no tz database: say so instead of guessing
        return now.strftime("%a %Y-%m-%d %H:%M") + " UTC (Pacific time unavailable)", utc
    hour = local.hour % 12 or 12
    return "%s %s %d:%02d %s %s" % (local.strftime("%a"), local.strftime("%Y-%m-%d"), hour, local.minute,
                                    "AM" if local.hour < 12 else "PM", local.tzname()), utc


def parse_header(text):
    """{'session', 'task', 'written', 'branch'} from the `Session:`, `Task:`, `Written:` and `Branch:` lines near
    the top of a handoff note. A missing line is None (notes written before P-54 have no `Branch:`)."""
    found = dict.fromkeys(("session", "task", "written", "branch"))
    for line in text.splitlines()[:HEADER_LINES]:
        name, sep, value = line.partition(":")
        key = name.strip().lower()
        if sep and key in found and found[key] is None and value.strip():
            found[key] = value.strip()
    return found


def read_header(handoff):
    """`parse_header` of the file; every field None when it cannot be read."""
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            return parse_header(f.read(4000))
    except OSError:
        return parse_header("")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sidecar_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".handoff.json") if name else None


def read_sidecar(root, session_id):
    """The session's `<id>.handoff.json` as a dict, or None."""
    path = sidecar_path(root, session_id)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_sidecar(root, session_id, handoff, check=None):
    """Record that this session wrote the file as it is now: {"sha256", "path", "written_epoch"}, and `check`
    (the handoff-versus-git cross-check, P-15) when there is one."""
    path = sidecar_path(root, session_id)
    if not path:
        return None
    data = {"sha256": file_sha256(handoff), "path": gwconfig.display_path(handoff, root),
            "written_epoch": os.path.getmtime(handoff)}
    if check is not None:
        data["cross_check"] = check
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def handoff_state(handoff, transcript=None, session_id=None, root=None):
    """{'exists', 'modified' (epoch), 'last_turn' (epoch), 'foreign', 'stale'}.

    Stale: no handoff, or foreign, or the session has a turn (not the wrap-up turn) after the file was last
    written. Without a transcript only a missing or foreign file is stale.

    Foreign (only checked when `session_id` is given): the file exists and this session has no sidecar
    (`.whatsnext/sessions/<id>.handoff.json`) or the sidecar's SHA-256 is not the file's. Another session
    wrote it, or it was edited since: it is not this session's note (ADR-0008). `root` is the
    project root; it is found from the file's folder when left out."""
    exists = os.path.isfile(handoff)
    modified = os.path.getmtime(handoff) if exists else None
    last = gwsessions.last_turn_time(transcript, PROMPT) if transcript and os.path.isfile(transcript) else None
    foreign = False
    if exists and session_id is not None:
        side = read_sidecar(root or gwconfig.find_root(os.path.dirname(handoff)), session_id)
        try:
            foreign = side is None or side.get("sha256") != file_sha256(handoff)
        except OSError:
            foreign = True
    stale = (not exists) or foreign or (last is not None and modified < last)
    return {"exists": exists, "modified": modified, "last_turn": last, "foreign": foreign, "stale": stale}


# ---- compacted without a wrap-up (P-4) ---------------------------------------


def compact_marker_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".compact.json") if name else None


def mark_compacted(root, session_id, when, carry=None):
    """Record that a compact is about to happen with no fresh handoff (`when` = UTC text) and, in `carry`, the
    short text the next resume note repeats (ADR-0015). With neither, clear an older record. Nothing is written
    without a usable session id."""
    path = compact_marker_path(root, session_id)
    if path is None:
        return None
    if when is None and not carry:
        if os.path.isfile(path):
            os.remove(path)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        state = {"session_id": session_id, "without_wrapup": when}
        if carry:
            state["carry"] = carry
        json.dump(state, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def summary_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".summary.md") if name else None


def plan_step_texts(task):
    """The text of each step in the task's Plan steps section."""
    from . import capture as gwcapture
    out = []
    for line in task.sections.get("plan steps", "").splitlines():
        m = gwcapture.STEP_RE.match(line.strip())
        if m:
            out.append(m.group(2).strip())
    return out


def kept_steps(summary, steps):
    """How many of `steps` the summary still names (case and spacing ignored)."""
    flat = " ".join((summary or "").lower().split())
    return sum(1 for step in steps if " ".join(step.lower().split()) in flat)


def save_summary(root, session_id, summary, task=None):
    """PostCompact: keep Claude Code's summary in git-ignored session state, the previous one as `.bak`, and record
    how many plan steps it still names. An empty summary writes a marker and no file. Returns the state dict."""
    path = summary_path(root, session_id)
    if path is None:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    state = {"session_id": session_id, "saved": gwstatus.stamp_time(), "ok": bool(isinstance(summary, str) and summary.strip())}
    if os.path.isfile(path):
        os.replace(path, path + ".bak")
    if state["ok"]:
        from . import redact as gwredact
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(gwredact.mask_secrets(summary))
        os.replace(tmp, path)
        if task is not None:  # 0 of 0: the task saved no steps, which the resume note says (P-64)
            steps = plan_step_texts(task)
            state["steps_total"], state["steps_kept"] = len(steps), kept_steps(summary, steps)
    with open(path[:-3] + ".json", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    return state


def summary_line(root, session_id):
    """The resume-note sentence about the saved summary, or None."""
    path = summary_path(root, session_id) if session_id else None
    try:
        with open(path[:-3] + ".json", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(state, dict):
        return None
    if not state.get("ok"):
        return "The compact summary was empty: do not trust it; the note below is the record."
    if state.get("steps_total") == 0:
        return "No plan steps were saved to check the summary against."
    if isinstance(state.get("steps_total"), int):
        return "Summary kept %d of %d plan steps." % (state.get("steps_kept", 0), state["steps_total"])
    return None


def resume_marker_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".resume.json") if name else None


def set_resume_marker(root, session_id):
    """Codex: a compact is coming and SessionStart may not say so. The next prompt prints the resume note once."""
    path = resume_marker_path(root, session_id)
    if path is None:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "set": gwstatus.stamp_time()}, f)
        f.write("\n")
    return path


def take_resume_marker(root, session_id):
    """True once after `set_resume_marker`: the marker is removed as it is read."""
    path = resume_marker_path(root, session_id) if session_id else None
    if path is None or not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


def compacted_without_wrapup(root, session_id):
    """The UTC text of the last compact with no fresh handoff in this session, or None."""
    path = compact_marker_path(root, session_id) if session_id else None
    try:
        with open(path, encoding="utf-8") as f:
            when = json.load(f).get("without_wrapup")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return when if isinstance(when, str) and when else None


def compacted_carry(root, session_id):
    """The text PreCompact saved for the resume note after the compact, or None."""
    path = compact_marker_path(root, session_id) if session_id else None
    try:
        with open(path, encoding="utf-8") as f:
            carry = json.load(f).get("carry")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return carry if isinstance(carry, str) and carry else None


# ---- wrap up: the hook ------------------------------------------------------


def marker_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".wrapup.json") if name else None


ALLOW_WINDOW_SECONDS = 30 * 60  # a wrap-up older than this no longer opens the permission


def safe_handoff_target(root, effective):
    """The handoff note's real path when it is safe to write without a prompt, else None. The repository's own
    settings and AGENTS.md choose this path, so it must be a plain `.md` file inside the project, outside every dot
    folder but `.whatsnext/` (`.git/`, `.claude/`, `.github/`), and neither it nor a folder above it may be a link."""
    inside = os.path.realpath(root)
    rel = os.path.relpath(handoff_path(root, effective), root)
    parts = rel.split(os.sep)
    if rel.startswith("..") or os.path.isabs(rel) or not rel.endswith(".md") or ".." in parts:
        return None
    if any(p.startswith(".") and not (i == 0 and p == ".whatsnext") for i, p in enumerate(parts)):
        return None
    lexical = os.path.normpath(os.path.join(inside, rel))
    if os.path.realpath(lexical) != lexical or os.path.commonpath([lexical, inside]) != inside:
        return None
    return lexical


def allow_handoff_write(root, effective, data):
    """PermissionRequest (P-43): the JSON that lets the agent write the handoff note while this session's `wrap up` is
    open, else "". It covers one file only (see `safe_handoff_target`), for 30 minutes after the request. The request
    marker `begin` writes is the proof the person (or the idle timer) asked for it, and `settle` removes it at Stop.
    Nothing is added to the person's settings."""
    path = marker_path(root, data.get("session_id"))
    tool_input = data.get("tool_input")
    target = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not path or not os.path.isfile(path) or not isinstance(target, str) or data.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            requested = float(json.load(f).get("requested_epoch"))
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if not 0 <= now_utc().timestamp() - requested <= ALLOW_WINDOW_SECONDS:
        return ""
    wanted = safe_handoff_target(root, effective)
    if wanted is None:
        return ""
    base = root  # not the hook's `cwd`: a relative target means a path under the project root
    given = target if os.path.isabs(target) else os.path.join(base, target)
    if os.path.realpath(given) != wanted:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}) + "\n"


def line_template():
    """The `/compact` line with a slot for each section, as the prompt shows it (the caps come from LINE_SECTIONS)."""
    slots = " ".join("%s: <%s, at most %d characters>" % (label, names[0].lower(), cap) for label, names, cap in LINE_SECTIONS)
    return "/compact " + LINE_BASE + " " + slots


def instructions(root, effective, now=None, session_id=None, agent=None):
    """The text the hook adds to the prompt `wrap up`. Codex (`agent == "codex"`) also gets the `/compact` line:
    Claude Code gets its PreCompact hook instead, so its reply ends with the handoff path and a plain `/compact` hint."""
    handoff = handoff_path(root, effective)
    rel = gwconfig.display_path(handoff, root)
    local, utc = pacific_now(now)
    folder = gwstatus.status_folder(root, effective)
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root),
                                session_id if isinstance(session_id, str) else None, root)
    lines = [
        "whatsnext: the user typed `%s`. Write the project's handoff note now. Ask nothing." % PROMPT,
        "",
        "File: %s (overwrite it). Time to write in it: %s (Pacific) = %s." % (rel, local, utc),
        "Read first: the old handoff when it exists; `git log` since its date and `git status`; the decisions in docs/decisions/ made since then.",
    ]
    if task is not None:
        lines.append("The active task is %s. Its progress file is %s: read it. When it has a `## Since wrap-up` section, "
                     "fold those lines into the note, then delete that section from the progress file." % (task.id, task.rel))
    lines += [
        "",
        "Write the file as a `# Handoff` title, then these four header lines exactly as shown, then these eight `##` sections, in this order. Short lines, plain words, no filler:",
        "Session: %s" % (session_id if isinstance(session_id, str) and session_id.strip() else "unknown"),
        "Task: %s" % (task.id if task is not None else "none"),
        "Written: %s" % utc,
        "Branch: %s" % (gwstatus.current_branch(root) or "none"),
        "",
        "1. `## Goal`: what the work is for, one or two lines (at most 200 characters).",
        "2. `## Next action`: the exact next step, one or two lines, with the command to run. Then a line `Verify: <the command or check that proves it worked>`, then a line `If it fails: <what to check or try next>`. Write paths relative to the repository root; never an absolute path, a home folder or the plugin's script path, because this file is committed and shared. At most 400 characters in all.",
        "3. `## State`: begin with `State on %s (Pacific): ` then where the work stands and what was last checked, with its result." % local,
        "4. `## What changed`: files and commits since the last handoff, one line each (at most 5 lines).",
        "5. `## Decisions`: what was decided and where it is recorded (ADR path); for a decision with no ADR, give the reason in a few words; `none` when nothing was. At most 400 characters.",
        "6. `## Constraints`: what the next session must keep: scope limits, files not to touch, the user's rules for this work, and the user's corrections to you in their own words; `none` when nothing. At most 600 characters.",
        "7. `## Open questions and blockers`: what the user still has to answer, what blocks the work, and work the user asked for that is not done; `none` when nothing. At most 300 characters.",
        "8. `## Dead ends`: approaches tried and dropped, one line each with the reason it was dropped; `none` when nothing. At most 300 characters.",
        "",
        "Write exact values, not descriptions of them: file paths, ids, versions, URLs, commands and error text as they appear. "
        "Use only facts from this session and the repository; mark a guess as a guess. Never write secrets. Do not commit.",
        "Do not write `## Files`, `## Links` or `## Skills` sections: whatsnext adds them from this session's tool calls when you stop.",
    ]
    if task is not None:
        lines.append("Do not run commands to update the progress file's Next action: whatsnext copies it from your note.")
    if agent == "codex":
        lines += [
            "",
            "End your reply with these three lines. The second is one line: copy it, and replace each <slot> with the text of the "
            "note's section of that name, cut to its limit. Next action and Constraints must fit as written. Change no other word. "
            "The whole line stays at most %d characters." % MAX_LINE_CHARS,
            "Handoff written: %s" % rel,
            line_template(),
            "or `/clear` for a fresh start",
        ]
    else:  # Claude Code: the PreCompact hook carries the handoff into the compact, so no /compact template is printed
        lines += [
            "",
            "End your reply with exactly these two lines and nothing after them:",
            "Handoff written: %s" % rel,
            "Choose above the prompt: Compact and continue here, or Copy for new session.",
        ]
    return "\n".join(lines) + "\n"


ARCHIVE_DIR = "handoffs"  # next to the handoff note: docs/project/handoffs/
ARCHIVE_KEEP = 10  # archived notes kept; the oldest go first
ARCHIVE_NAME_RE = re.compile(r"^\d{8}T\d{4}Z-[A-Za-z0-9._-]{1,40}(-\d+)?\.md$")  # only files the archive wrote


def archive_handoff(root, effective, keep=ARCHIVE_KEEP):
    """Before `wrap up` overwrites the note, save the old one as `<folder>/handoffs/<Written, UTC>-<task>.md`.
    A note that is already saved (same content) is not saved twice. Only the newest `keep` are kept.
    Returns the saved path, or None when there was nothing to save."""
    handoff = handoff_path(root, effective)
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except OSError:
        return None
    if not body.strip():
        return None
    header = parse_header(body)
    written = gwclaims.to_dt(header["written"]) if header["written"] else None
    when = (written or datetime.datetime.fromtimestamp(os.path.getmtime(handoff), datetime.timezone.utc)
            ).astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%MZ")
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", header["task"] or header["session"] or "note").strip("-")[:40] or "note"
    folder = os.path.join(os.path.dirname(handoff), ARCHIVE_DIR)
    if os.path.islink(folder):  # the archive folder is a real folder or nothing: a link could point anywhere
        return None
    inside = os.path.realpath(root)  # no link on the way (a linked `docs/project`, say) may lead outside the project
    parent = os.path.realpath(os.path.dirname(folder))
    if os.path.commonpath([parent, inside]) != inside:
        return None
    os.makedirs(folder, exist_ok=True)
    digest = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
    for name in os.listdir(folder):
        if ARCHIVE_NAME_RE.match(name) and not os.path.islink(os.path.join(folder, name)):
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                    if hashlib.sha256(f.read().encode("utf-8", "replace")).hexdigest() == digest:
                        return None
            except OSError:
                continue
    path = os.path.join(folder, "%s-%s.md" % (when, label))
    n = 1
    while os.path.lexists(path):  # lexists: a dangling link is taken too, never written through
        n += 1
        path = os.path.join(folder, "%s-%s-%d.md" % (when, label, n))
    write_atomic(path, body)
    names = sorted(n for n in os.listdir(folder)
                   if ARCHIVE_NAME_RE.match(n) and not os.path.islink(os.path.join(folder, n)))
    for old in names[:max(len(names) - keep, 0)]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    return path


def latest_handoff(root, effective, task_id):
    """P-57: the newest note whose `Task:` is `task_id`, from the handoff note and its archive folder, as
    (path, written) with `written` an aware datetime (the `Written:` time, else the file's time). The handoff note
    wins a tie: an archived copy of it has the same time. Links are never read. None when no note is for the task."""
    want = task_id.strip().lower()
    handoff = handoff_path(root, effective)
    paths = [handoff]
    folder = os.path.join(os.path.dirname(handoff), ARCHIVE_DIR)
    if os.path.isdir(folder) and not os.path.islink(folder):
        try:
            paths += [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if ARCHIVE_NAME_RE.match(n)]
        except OSError:
            pass
    best = None
    for path in paths:
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        header = read_header(path)
        if (header["task"] or "").strip().lower() != want:
            continue
        written = gwclaims.to_dt(header["written"]) if header["written"] else None
        if written is None:
            try:
                written = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
            except OSError:
                continue
        if best is None or written > best[1]:
            best = (path, written)
    return best


def begin(root, effective, data, agent=None):
    """Remember the request, save the old note, and return the instructions to print."""
    try:
        archive_handoff(root, effective)
    except Exception:  # an archive that fails must not stop the wrap-up
        pass
    path = marker_path(root, data.get("session_id"))
    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"requested": gwstatus.stamp_time(), "requested_epoch": now_utc().timestamp()}, f)
                f.write("\n")
        except OSError:  # the event is lost, the note is not
            pass
    return instructions(root, effective, session_id=data.get("session_id"), agent=agent)


def settle(root, effective, data, agent=None):
    """At Stop: when a wrap-up was requested in this session and the handoff was written since, record it.
    Returns True when recorded. The request marker is always removed."""
    path = marker_path(root, data.get("session_id"))
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            requested = float(json.load(f).get("requested_epoch"))
    except (OSError, ValueError, TypeError, AttributeError):
        requested = None
    try:
        os.remove(path)
    except OSError:
        pass
    handoff = handoff_path(root, effective)
    # File times have a coarser tick than the clock: allow one second.
    if requested is None or not os.path.isfile(handoff) or os.path.getmtime(handoff) < requested - 1:
        return False
    try:
        add_used_sections(root, effective, handoff, data)
    except Exception:  # the sections are a help; recording the wrap-up is what matters
        pass
    folder = gwstatus.status_folder(root, effective)
    sid = data.get("session_id")
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root),
                                sid if isinstance(sid, str) else None, root)
    payload = {"session": data.get("session_id"), "handoff": gwconfig.display_path(handoff, root),
               "task": task.id if task else None, "agent": agent or "claude-code"}
    try:
        gwbackend.get_backend(effective).emit("session.wrapup", payload)
    except Exception:  # a backend problem must not stop the journal line
        pass
    try:
        from . import crosscheck as gwcrosscheck
        try:
            check = gwcrosscheck.cross_check(root, effective, handoff, task)
        except Exception:  # the check is a help; the sidecar is what matters
            check = None
        write_sidecar(root, data.get("session_id"), handoff, check)
    except OSError:  # without it the note counts as foreign: a stale answer, never a wrong one
        pass
    gwjournal.record(root, effective, "wrap-up", data)
    if task is not None:
        copy_next_action(root, folder, task, handoff)
    return True


def previous_wrapup_time(root, effective, session_id):
    """Epoch seconds of this session's previous wrap-up: the `Written:` time of the newest archived note it wrote,
    or None. `begin` archived the old note, so the archive holds every earlier note."""
    folder = os.path.join(os.path.dirname(handoff_path(root, effective)), ARCHIVE_DIR)
    try:
        names = sorted((n for n in os.listdir(folder) if ARCHIVE_NAME_RE.match(n)), reverse=True)
    except OSError:
        return None
    for name in names:
        header = read_header(os.path.join(folder, name))
        if header["session"] == session_id and header["written"]:
            written = gwclaims.to_dt(header["written"])
            return written.timestamp() if written else None
    return None


def add_used_sections(root, effective, handoff, data):
    """P-68: add the Files, Links and Skills sections to the note just written, from this session's tool calls
    since its previous wrap-up (the whole session when there was none). Returns the facts, or None."""
    from . import used as gwused
    sid = data.get("session_id")
    if not gwsessions.valid_session_id(sid):
        return None
    transcript = data.get("transcript_path")
    if not (isinstance(transcript, str) and os.path.isfile(transcript)):
        transcript = gwsessions.find_transcript(sid)
    def rel(path):  # relative to the project root, as `used` writes paths
        return os.path.relpath(path, root).replace(os.sep, "/")
    skip = (rel(handoff), rel(os.path.join(os.path.dirname(handoff), ARCHIVE_DIR)) + "/", ".whatsnext/")
    return gwused.write_sections(root, handoff, transcript, previous_wrapup_time(root, effective, sid), skip,
                                 MAX_HANDOFF_CHARS)


def section_text(body, names):
    """The text of the first section of `body` that one of `names` titles, white space joined; '' when none."""
    lines = body.split("\n")
    for name in names:
        text = " ".join(gwstatus.get_section(lines, name).split())
        if text:
            return text
    return ""


def handoff_next(handoff):
    """The note's Next action section (with its Verify line) as one line, or ''."""
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            return section_text(f.read(), ("Next action",))
    except OSError:
        return ""


def copy_next_action(root, folder, task, handoff):
    """Write the handoff's Next action into the task's progress file as an `auto` note (a guess by the
    model): it never replaces a confirmed Next action, it goes under `## Since wrap-up` (ADR-0002)."""
    try:
        text = handoff_next(handoff)
        if text:
            gwstatus.write_next(root, folder, task.id, text[:MAX_NEXT_CHARS], "auto")
    except (OSError, gwstatus.FormatError):
        pass


# ---- compact instructions ---------------------------------------------------


def clip_to(text, limit):
    """`text` cut to exactly `limit` characters at most, ending in an ellipsis when it was cut."""
    return text if len(text) <= limit else text[:max(limit - 1, 0)].rstrip() + "\u2026"


def compact_line(body):
    """The one-line `/compact <text>` for a handoff note: LINE_BASE, then `Label: text` for each section the
    note has, at most MAX_LINE_CHARS in all. Each section is cut at its cap (LINE_SECTIONS). When the line is
    still too long, Blockers, Decisions and Goal are cut or dropped, in that order; Next and Constraints never are."""
    values = {}
    for label, names, cap in LINE_SECTIONS:
        text = section_text(body, names)
        if text and text.strip(" .").lower() != "none":
            values[label] = clip_to(text, cap)

    def build():
        return "/compact " + " ".join([LINE_BASE] + ["%s: %s" % (label, values[label])
                                                      for label, _n, _c in LINE_SECTIONS if label in values])

    line = build()
    for label in LINE_SHRINK:
        over = len(line) - MAX_LINE_CHARS
        if over <= 0:
            break
        if label not in values:
            continue
        room = len(values[label]) - over
        if room >= LINE_MIN_SLOT:
            values[label] = clip_to(values[label], room)
        else:
            del values[label]
        line = build()
    return line


def fit_body(body, limit, rel):
    """The note as the compact text carries it: whole when it fits, else its header and as many sections as fit,
    most important first (Next action, Constraints, Goal, Decisions, Open questions and blockers, State, What
    changed). A note without any `##` section is cut at `limit`."""
    if len(body) <= limit:
        return body
    marker = "\n(handoff cut here; the rest is in %s)" % rel
    lines = body.split("\n")
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), None)
    if first is None:
        return body[:limit].rstrip() + marker
    pieces = ["\n".join(lines[:first]).strip()]
    room = limit - len(pieces[0])
    for name in BODY_ORDER:
        text = gwstatus.get_section(lines, name)
        if not text:
            continue
        chunk = "## %s\n%s" % (name, text)
        if len(chunk) + 2 <= room:
            pieces.append(chunk)
            room -= len(chunk) + 2
        elif room > 80:
            pieces.append(chunk[:room - 2].rstrip())
            break
    return "\n\n".join(p for p in pieces if p) + marker


def compact_instructions(root, effective, session_id=None):
    """The text after `/compact `: what to keep and drop, then the handoff note when there is one.
    With a `session_id`, a note this session did not write (foreign, ADR-0008) is not carried:
    the text says another session wrote it and where it is."""
    handoff = handoff_path(root, effective)
    text = COMPACT_BASE
    if os.path.isfile(handoff):
        rel = gwconfig.display_path(handoff, root)
        if session_id is not None and handoff_state(handoff, None, session_id, root)["foreign"]:
            return text + "\n\nA handoff note exists at %s, but this session did not write it, so it is not carried here. " \
                          "Read it only if it fits this task." % rel
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read().strip()
        body = fit_body(body, MAX_HANDOFF_CHARS, rel)
        if body:
            text += "\n\nThe project's handoff note (%s) says where the work stands. Carry it into the summary:\n%s" % (rel, body)
    return text


def say(message):
    print(message, file=sys.stderr)
