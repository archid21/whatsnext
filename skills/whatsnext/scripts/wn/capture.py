"""Plan-mode capture (`progress capture`, ADR-0006).

`shown` stores the plan word for word in `<paths.plans>/<task>-<YYYY-MM-DD>.md`
behind a short header, and writes at most MAX_STEPS checklist lines under
"## Plan steps" in the task's progress file. `approved` and `unapproved` only
change the status, in the plan file and in the progress file's Plan field.
Plain code, no model call. Private text is removed before anything is split or
written. The command never edits PLAN.md.
"""

import os
import re
import sys

from . import config as gwconfig
from . import redact as gwredact
from . import status as gwstatus
from .util import now_utc

STATUSES = ("shown", "approved", "unapproved")
STATUS_TEXT = {"shown": "shown", "approved": "approved", "unapproved": "used without approval"}
MAX_STEPS = 20
MAX_STEP = 160
STEPS_HEADING = "## Plan steps"
MORE_RE = re.compile(r"^…\s*(\d+) more in the plan file\s*$")
STEP_RE = re.compile(r"^- \[([ xX])\]\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
H2_RE = re.compile(r"^##(?!#)\s+(.*?)\s*#*\s*$")
NUMBERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s+")
PLAN_FIELD_RE = re.compile(r"^(.*?)\s+\(([^()]*)\)$")
STEPS_H2_RE = re.compile(r"^##(?!#)\s+.*\bsteps\b", re.IGNORECASE)


# ---- split -----------------------------------------------------------------


def clean_step(text):
    text = " ".join(CHECKBOX_RE.sub("", text.strip()).split())
    return text if len(text) <= MAX_STEP else text[:MAX_STEP - 1].rstrip() + "…"


def section_lines(lines, heading_re):
    """Lines under the first `##` heading matching heading_re, up to the next `##` heading."""
    out, inside = [], False
    for line in lines:
        if H2_RE.match(line):
            if inside:
                break
            inside = bool(heading_re.match(line))
        elif inside:
            out.append(line)
    return out


def list_items(lines):
    """The least-indented numbered items, else the least-indented `- ` items."""
    for pattern in (NUMBERED_RE, BULLET_RE):
        found = [m for m in (pattern.match(l) for l in lines) if m]
        if found:
            indent = min(len(m.group(1)) for m in found)
            return [m.group(2) for m in found if len(m.group(1)) == indent]
    return []


def split_steps(text):
    """Steps of a plan: the list items under a `## Steps` heading when there is one (Claude Code
    plans use `## Context / ## Steps / ## Verification`), else `##` headings, else the
    least-indented numbered items, else `- ` items, else the first line. Lines inside code
    fences are skipped."""
    lines = []
    fenced = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append(line)
    steps = list_items(section_lines(lines, STEPS_H2_RE))
    if not steps:
        steps = [m.group(1) for m in (H2_RE.match(l) for l in lines) if m]
    if not steps:
        steps = list_items(lines)
    if not steps:
        first = next((l for l in lines if l.strip()), "")
        steps = [first.lstrip("#")] if first else []
    return [s for s in (clean_step(s) for s in steps) if s]


def steps_section(steps):
    lines = [STEPS_HEADING, ""] + ["- [ ] " + s for s in steps[:MAX_STEPS]]
    if len(steps) > MAX_STEPS:
        lines.append("… %d more in the plan file" % (len(steps) - MAX_STEPS))
    return lines


def read_steps(task):
    """(number of the first open step or None, its text or None, total) from the Plan steps section.
    When every listed step is checked and more are in the plan file, the next one is open there."""
    steps, more = [], 0
    for line in task.sections.get("plan steps", "").splitlines():
        m = STEP_RE.match(line.strip())
        if m:
            steps.append((m.group(1) == " ", m.group(2).strip()))
        elif MORE_RE.match(line.strip()):
            more = int(MORE_RE.match(line.strip()).group(1))
    total = len(steps) + more
    for n, (is_open, text) in enumerate(steps, 1):
        if is_open:
            return n, text, total
    return (len(steps) + 1, None, total) if more else (None, None, total)


def plan_field(task):
    """(path, status text) from the progress file's Plan field, or (None, None)."""
    value = task.field("plan")
    if not value:
        return None, None
    m = PLAN_FIELD_RE.match(value)
    return (m.group(1), m.group(2)) if m else (value, "")


def resume_line(task):
    """'Plan: <path>, step N of M: <step>' for the resume note, or None when no plan is captured."""
    path, status = plan_field(task)
    if not path:
        return None
    if status and status != STATUS_TEXT["approved"]:
        path = "%s (%s)" % (path, status)
    n, step, total = read_steps(task)
    if not total:
        return "Plan: %s" % path
    if n is None:
        return "Plan: %s, all %d steps checked" % (path, total)
    return "Plan: %s, step %d of %d: %s" % (path, n, total, step or "see the plan file")


# ---- plan files ------------------------------------------------------------


def plan_header(task_id, agent, when, status):
    return ["# Plan: %s" % task_id, "", "- **Agent:** %s" % agent, "- **Time:** %s" % when,
            "- **Status:** %s" % STATUS_TEXT[status], ""]


def header_fields(lines):
    """{lower name: line index} of the header fields that follow the title line."""
    out = {}
    for i in range(2, len(lines)):
        m = gwstatus.FIELD_RE.match(lines[i].rstrip("\r"))
        if not m:
            break
        out[m.group(1).strip().lower()] = i
    return out


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read().split("\n")


def file_status(path):
    lines = read_lines(path)
    i = header_fields(lines).get("status")
    return gwstatus.FIELD_RE.match(lines[i].rstrip("\r")).group(2).strip() if i is not None else ""


def plan_path(folder, task_id, day):
    """The file for a new `shown` plan: the latest one for this task and day while it is only
    shown (the last plan shown wins), else the next free `-2`, `-3`, ... name."""
    base = os.path.join(folder, "%s-%s" % (task_id, day))
    latest, n = None, 1
    while os.path.exists(base + (".md" if n == 1 else "-%d.md" % n)):
        latest = base + (".md" if n == 1 else "-%d.md" % n)
        n += 1
    if latest and file_status(latest) == STATUS_TEXT["shown"]:
        return latest
    return base + (".md" if n == 1 else "-%d.md" % n)


# ---- progress file ---------------------------------------------------------


def replace_steps(lines, new):
    """`lines` with the Plan steps section replaced by `new`, or added after Next action."""
    def h2(i):
        return gwstatus.H2_RE.match(lines[i].rstrip("\r"))

    start = next((i for i in range(len(lines)) if h2(i) and h2(i).group(1).strip().lower() == "plan steps"), None)
    if start is None:
        after = next((i for i in range(len(lines)) if h2(i) and h2(i).group(1).strip().lower() == "next action"), None)
        if after is None:
            body = lines[:]
            while body and not body[-1].strip():
                body.pop()
            return body + [""] + new + [""]
        start = end = next((i for i in range(after + 1, len(lines)) if h2(i)), len(lines))
    else:
        end = next((i for i in range(start + 1, len(lines)) if h2(i)), len(lines))
    return lines[:start] + new + [""] + lines[end:]


def write_progress(task, plan_rel, status, steps=None):
    lines = read_lines(task.path)
    gwstatus.set_field(lines, "Plan", "%s (%s)" % (plan_rel, STATUS_TEXT[status]))
    gwstatus.set_field(lines, "Updated", gwstatus.stamp_time())
    if steps is not None:
        lines = replace_steps(lines, steps_section(steps))
    gwstatus.write_text(task.path, "\n".join(lines), warn=False)


# ---- command ---------------------------------------------------------------


def find_task(root, folder, task_id, session=None):
    """(task, error message). `session` (or $WHATSNEXT_SESSION) makes the active item that session claimed come first."""
    if task_id:
        problem = gwstatus.bad_id(task_id)
        if problem:
            return None, problem
        task = next((t for t in gwstatus.load_tasks(root, folder) if t.id == task_id), None)
        if task is None:
            return None, "no progress file for %s. Create it: `progress new %s --title \"...\"`." % (task_id, task_id)
        return task, None
    task = gwstatus.active_task(gwstatus.load_tasks(root, folder), gwstatus.current_branch(root),
                                session or gwstatus.env_session(), root)
    if task is None:
        return None, "no active task. Name one: `progress capture <task-id> ...`."
    return task, None


def read_plan_text(args):
    if getattr(args, "text", None) is not None:  # from a hook, which has read stdin already
        return args.text, None
    if args.file:
        try:
            with open(args.file, encoding="utf-8", errors="replace") as f:
                return f.read(), None
        except OSError as e:
            return None, "cannot read %s: %s" % (args.file, e.strerror or e)
    if sys.stdin is None or sys.stdin.isatty():
        return None, "no plan text: pass --file <path> or send the plan on stdin."
    return sys.stdin.read(), None


def capture_shown(root, effective, task, args):
    text, problem = read_plan_text(args)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    folder = os.path.join(root, effective.get("paths.plans"))
    text = gwredact.clean(text, "plan for %s" % task.id)  # before the split: private text never becomes a step
    if not text.strip():
        print("no plan text: the plan is empty.", file=sys.stderr)
        return 1
    now = now_utc()
    path = plan_path(folder, task.id, now.strftime("%Y-%m-%d"))
    agent = " ".join((args.agent or os.environ.get("WHATSNEXT_AGENT") or os.environ.get("GROUNDWORK_AGENT") or "").split()) or "unknown"
    body = "\n".join(plan_header(task.id, agent, now.strftime("%Y-%m-%dT%H:%MZ"), "shown")) + "\n" + text
    gwstatus.write_text(path, body if body.endswith("\n") else body + "\n", warn=False)
    rel = gwconfig.display_path(path, root)
    steps = split_steps(text)
    write_progress(task, rel, "shown", steps)
    print("captured %s (%d step%s in %s)" % (rel, len(steps), "" if len(steps) == 1 else "s", task.rel))
    gwstatus.emit(effective, task.id, task.rel, "capture")
    return 0


def capture_status(root, effective, task, args):
    rel, current = plan_field(task)
    path = os.path.join(root, rel) if rel else None
    if not path or not os.path.isfile(path):
        print("no captured plan for %s. Capture one first: `progress capture %s --status shown`." % (task.id, task.id),
              file=sys.stderr)
        return 1
    if current != STATUS_TEXT["shown"]:
        print("%s is already %s; unchanged." % (rel, current or "marked"))
        return 0
    lines = read_lines(path)
    i = header_fields(lines).get("status")
    if i is None:
        print("%s has no Status field; unchanged." % rel, file=sys.stderr)
        return 1
    lines[i] = "- **Status:** %s" % STATUS_TEXT[args.status]
    gwstatus.write_text(path, "\n".join(lines), warn=False)
    write_progress(task, rel, args.status)
    print("%s: %s" % (rel, STATUS_TEXT[args.status]))
    gwstatus.emit(effective, task.id, task.rel, "capture")
    return 0


def run(root, folder, effective, args):
    task, problem = find_task(root, folder, args.task_id, getattr(args, "session", None))
    if problem:
        print(problem, file=sys.stderr)
        return 1
    if args.status == "shown":
        return capture_shown(root, effective, task, args)
    return capture_status(root, effective, task, args)
