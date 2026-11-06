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
from . import config as gwconfig
from . import journal as gwjournal
from . import sessions as gwsessions
from . import status as gwstatus
from .util import now_utc

PROMPT = "wrap up"
DEFAULT_HANDOFF = "docs/project/HANDOFF.md"
TIMEZONE = "America/Los_Angeles"
MAX_HANDOFF_CHARS = 3000
MAX_NEXT_CHARS = 300
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
    """{'session', 'task', 'written'} from the `Session:`, `Task:` and `Written:` lines near the top of a
    handoff note. A missing line is None."""
    found = dict.fromkeys(("session", "task", "written"))
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


def write_sidecar(root, session_id, handoff):
    """Record that this session wrote the file as it is now: {"sha256", "path", "written_epoch"}."""
    path = sidecar_path(root, session_id)
    if not path:
        return None
    data = {"sha256": file_sha256(handoff), "path": gwconfig.display_path(handoff, root),
            "written_epoch": os.path.getmtime(handoff)}
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


def mark_compacted(root, session_id, when):
    """Record that a compact is about to happen with no fresh handoff (`when` = UTC text), or, when `when` is
    None, clear an older record. Nothing is written without a usable session id."""
    path = compact_marker_path(root, session_id)
    if path is None:
        return None
    if when is None:
        if os.path.isfile(path):
            os.remove(path)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "without_wrapup": when}, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def compacted_without_wrapup(root, session_id):
    """The UTC text of the last compact with no fresh handoff in this session, or None."""
    path = compact_marker_path(root, session_id) if session_id else None
    try:
        with open(path, encoding="utf-8") as f:
            when = json.load(f).get("without_wrapup")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return when if isinstance(when, str) and when else None


# ---- wrap up: the hook ------------------------------------------------------


def marker_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".wrapup.json") if name else None


def line_template():
    """The `/compact` line with a slot for each section, as the prompt shows it (the caps come from LINE_SECTIONS)."""
    slots = " ".join("%s: <%s, at most %d characters>" % (label, names[0].lower(), cap) for label, names, cap in LINE_SECTIONS)
    return "/compact " + LINE_BASE + " " + slots


def instructions(root, effective, now=None, session_id=None):
    """The text the hook adds to the prompt `wrap up`."""
    handoff = handoff_path(root, effective)
    rel = gwconfig.display_path(handoff, root)
    local, utc = pacific_now(now)
    folder = gwstatus.status_folder(root, effective)
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root))
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
        "Write the file as a `# Handoff` title, then these three header lines exactly as shown, then these eight `##` sections, in this order. Short lines, plain words, no filler:",
        "Session: %s" % (session_id if isinstance(session_id, str) and session_id.strip() else "unknown"),
        "Task: %s" % (task.id if task is not None else "none"),
        "Written: %s" % utc,
        "",
        "1. `## Goal`: what the work is for, one or two lines (at most 200 characters).",
        "2. `## Next action`: the exact next step, one or two lines, with the command to run. Then a line `Verify: <the command or check that proves it worked>`. Write paths relative to the repository root; never an absolute path, a home folder or the plugin's script path, because this file is committed and shared. At most 300 characters in all.",
        "3. `## State`: begin with `State on %s (Pacific): ` then where the work stands and what was last checked, with its result." % local,
        "4. `## What changed`: files and commits since the last handoff, one line each (at most 5 lines).",
        "5. `## Decisions`: what was decided and where it is recorded (ADR path); `none` when nothing was. At most 400 characters.",
        "6. `## Constraints`: what the next session must keep: scope limits, files not to touch, the user's rules for this work; `none` when nothing. At most 600 characters.",
        "7. `## Open questions and blockers`: what the user still has to answer and what blocks the work; `none` when nothing. At most 300 characters.",
        "8. `## Dead ends`: approaches tried and dropped, one line each with the reason it was dropped; `none` when nothing. At most 300 characters.",
        "",
        "Use only facts from this session and the repository; mark a guess as a guess. Never write secrets. Do not commit.",
    ]
    if task is not None:
        lines.append("Do not run commands to update the progress file's Next action: whatsnext copies it from your note.")
    lines += [
        "",
        "End your reply with these three lines. The second is one line: copy it, and replace each <slot> with the text of the "
        "note's section of that name, cut to its limit. Next action and Constraints must fit as written. Change no other word. "
        "The whole line stays at most %d characters." % MAX_LINE_CHARS,
        "Handoff written: %s" % rel,
        line_template(),
        "or `/clear` for a fresh start",
    ]
    return "\n".join(lines) + "\n"


def begin(root, effective, data):
    """Remember the request, and return the instructions to print."""
    path = marker_path(root, data.get("session_id"))
    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"requested": gwstatus.stamp_time(), "requested_epoch": now_utc().timestamp()}, f)
                f.write("\n")
        except OSError:  # the event is lost, the note is not
            pass
    return instructions(root, effective, session_id=data.get("session_id"))


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
    folder = gwstatus.status_folder(root, effective)
    task = gwstatus.branch_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root))
    payload = {"session": data.get("session_id"), "handoff": gwconfig.display_path(handoff, root),
               "task": task.id if task else None, "agent": agent or "claude-code"}
    try:
        gwbackend.get_backend(effective).emit("session.wrapup", payload)
    except Exception:  # a backend problem must not stop the journal line
        pass
    try:
        write_sidecar(root, data.get("session_id"), handoff)
    except OSError:  # without it the note counts as foreign: a stale answer, never a wrong one
        pass
    gwjournal.record(root, effective, "wrap-up", data)
    if task is not None:
        copy_next_action(root, folder, task, handoff)
    return True


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
