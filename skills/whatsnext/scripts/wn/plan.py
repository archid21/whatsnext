"""The plan checklist, Start, and items in progress (ADR-0002).

`PLAN.md` (paths.plan) is the single source. Scripts do the structure and the
git work; the agent asks the user. A command that needs an answer prints the
question and exits 4 (see `ask`); the agent asks, then runs the same command
again with the answer flag. Exit codes: 0 done, 1 error, 3 module off,
4 needs an answer.
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

from . import backend as gwbackend
from . import claims as gwclaims
from . import config as gwconfig
from . import journal as gwjournal
from . import redact as gwredact
from . import status as gwstatus
from .ask import NEEDS_ANSWER, ask, option
from .util import now_utc

SECTIONS = ("Now", "Next", "Later")
OTHER = "Other"
ID_PATTERN = r"[A-Z][A-Z0-9]*-\d+"
ITEM_RE = re.compile(r"^(\s*[-*]\s+)\[([ xX])\](\s+)(%s)\b(.*)$" % ID_PATTERN)
HEADING_RE = re.compile(r"^(#{1,2})\s+(.*?)\s*#*\s*$")
FIELD_SPLIT_RE = re.compile(r"\s+·\s+|\s+-\s+(?=done means:)", re.I)
FIELD_RE = re.compile(r"^(done means|evidence)\s*:\s*(.*)$", re.I)
UNVERIFIED = "checked by a person, not verified"
UNVERIFIED_MARK = "*"  # `plan list` shows "done*" and one footnote instead of UNVERIFIED on each row
VERIFIED_PREFIX = "verified:"  # evidence that `plan done --verify` wrote after a passing command (ADR-0003)
VERIFY_TIMEOUT_RE = re.compile(r"^([1-9][0-9]*)([smh])$")
VERIFY_TIMEOUT_DEFAULT = 30 * 60  # seconds, when plan.verifyTimeout cannot be read
VERIFY_TAIL_LINES = 20  # output lines kept in the journal after a failed verify
VERIFY_LINE_MAX = 200
VERIFY_CMD_MAX = 120  # characters of the command shown in PLAN.md and messages
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
FIRST_STEP = "Restate the goal and done means, list 3 to 5 steps, and wait for the user's OK."
NEXT_STEP = FIRST_STEP[:-1] + " before changing files."
BRANCH_CHOICES = ("branch", "stay", "worktree")
MAX_SLUG = 40


# ---- parsing ---------------------------------------------------------------


class Item(object):
    """One checklist line."""

    def __init__(self, item_id, title, checked, done_means, evidence, section, index):
        self.id = item_id
        self.title = title
        self.checked = checked
        self.done_means = done_means
        self.evidence = evidence
        self.section = section
        self.index = index  # line number (0-based) in the file


def strip_comments(line, in_comment):
    """(`line` without HTML comments, still inside a comment at the line end)."""
    out = []
    i = 0
    while i < len(line):
        if in_comment:
            j = line.find("-->", i)
            if j < 0:
                return "".join(out), True
            i, in_comment = j + 3, False
        else:
            j = line.find("<!--", i)
            if j < 0:
                out.append(line[i:])
                break
            out.append(line[i:j])
            i, in_comment = j + 4, True
    return "".join(out), in_comment


def parse_rest(rest):
    """(title, done means, evidence) from the text after the item id."""
    rest = rest.strip()
    if rest.startswith(":"):
        rest = rest[1:].strip()
    title, done_means, evidence = None, "", ""
    for part in FIELD_SPLIT_RE.split(rest):
        part = part.strip()
        m = FIELD_RE.match(part)
        if m:
            if m.group(1).lower() == "evidence":
                evidence = evidence or m.group(2).strip()
            else:
                done_means = done_means or m.group(2).strip()
        elif title is None:
            title = part
    return title or "", done_means, evidence


def parse_text(text):
    """(lines, items). Lines keep their line ends; items are in file order."""
    lines = text.split("\n")
    items = []
    section = OTHER
    in_comment = False
    for i, raw in enumerate(lines):
        visible, in_comment = strip_comments(raw.rstrip("\r"), in_comment)
        h = HEADING_RE.match(visible)
        if h:
            name = h.group(2).strip()
            section = next((s for s in SECTIONS if s.lower() == name.lower()), OTHER) if h.group(1) == "##" else OTHER
            continue
        m = ITEM_RE.match(visible)
        if m:
            title, done_means, evidence = parse_rest(m.group(5))
            items.append(Item(m.group(4), title, m.group(2) in "xX", done_means, evidence, section, i))
    return lines, items


def read_plan(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def rewrite_item(path, item_id, transform):
    """Re-read the file, change only the first line of item `item_id`, write it back.

    `transform` gets the line without its line end and returns the new line.
    Returns False when the item is not in the file.
    """
    lines, items = parse_text(read_plan(path))
    item = next((it for it in items if it.id == item_id), None)
    if item is None:
        return False
    raw = lines[item.index]
    tail = "\r" if raw.endswith("\r") else ""
    lines[item.index] = transform(raw[:len(raw) - len(tail)]) + tail
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    return True


def clean(text):
    return " ".join((text or "").replace("·", "-").split())


def is_verified(evidence):
    """True when a command proved the item (`plan done --verify`). Any other evidence is a person's word."""
    return (evidence or "").lower().startswith(VERIFIED_PREFIX)


def with_field(line, field):
    """`line` with ` · <field>` added before an evidence field, else at the end."""
    m = re.search(r"\s+·\s+evidence\s*:", line, re.I)
    if m:
        return line[:m.start()] + " · " + field + line[m.start():]
    return line.rstrip() + " · " + field


# ---- context and views -----------------------------------------------------


class Ctx(object):
    def __init__(self, root, effective):
        self.root = root
        self.effective = effective
        self.plan_rel = effective.get("paths.plan")
        self.plan_path = os.path.join(root, self.plan_rel)
        self.folder = gwstatus.status_folder(root, effective)
        self.stale_after = effective.get("plan.staleAfter")
        self.now = now_utc()

    @classmethod
    def load(cls, cwd=None):
        root = gwconfig.find_root(cwd)
        return cls(root, gwconfig.load(root))

    def has_plan(self):
        return os.path.isfile(self.plan_path)

    def items(self):
        return parse_text(read_plan(self.plan_path))[1] if self.has_plan() else []

    def tasks(self):
        return {t.id: t for t in gwstatus.load_tasks(self.root, self.folder)}

    def views(self, items=None):
        items = self.items() if items is None else items
        tasks, claim_map = self.tasks(), gwclaims.read_all(self.root)
        return [self.view(it, tasks.get(it.id), claim_map.get(it.id)) for it in items]

    def view(self, item, task, claim):
        stale, idle = False, None
        if item.checked:
            status = "done"
        elif task is not None and task.state == "blocked":
            status = "blocked"
        elif claim:
            status = "in progress"
            updated = task.field("updated") if task is not None else None
            stale = gwclaims.is_stale(claim, updated, self.stale_after, self.now)
            idle = gwclaims.idle_since(claim, updated)
        else:
            status = "open"
        info = None
        if claim:
            since = gwclaims.to_dt(claim.get("since"))
            info = {"agent": claim.get("agent"), "branch": claim.get("branch"), "session": claim.get("session"),
                    "worktree": claim.get("worktree"), "since": claim.get("since"),
                    "since_short": gwclaims.short_time(since, self.now) if since else "unknown",
                    "idle_since": gwclaims.stamp(idle) if idle else None,
                    "idle_short": gwclaims.short_time(idle, self.now) if idle else "unknown", "stale": stale}
        return {"id": item.id, "title": item.title, "section": item.section, "status": status,
                "done_means": item.done_means, "evidence": item.evidence,
                "verified": is_verified(item.evidence) if item.checked else None,
                "stale": stale, "claim": info}

    def emit(self, event, payload):
        try:
            gwbackend.get_backend(self.effective).emit(event, payload)
        except (gwbackend.BackendError, ValueError, OSError) as e:
            print("warning: backend event %s not delivered: %s" % (event, e), file=sys.stderr)


def fail(message):
    print(message, file=sys.stderr)
    return 1


def no_plan(ctx):
    return "No plan file at %s." % ctx.plan_rel


def agent_name(args):
    return " ".join((getattr(args, "agent", None) or os.environ.get("WHATSNEXT_AGENT") or os.environ.get("GROUNDWORK_AGENT") or "").split()) or "unknown"


def describe_claim(info):
    text = "in progress (%s" % info["agent"]
    if info["branch"]:
        text += " · %s" % info["branch"]
    text += " · since %s" % info["since_short"]
    if info["stale"]:
        text += " · stale, idle since %s" % info["idle_short"]
    return text + ")"


def status_text(view):
    if view["status"] == "done":
        return "done" if view["verified"] else "done" + UNVERIFIED_MARK
    if view["status"] == "in progress" and view["claim"]:
        return describe_claim(view["claim"])
    return view["status"]


# ---- list, next, check -----------------------------------------------------


def cmd_list(ctx, args):
    if not ctx.has_plan():
        if args.json:
            print(json.dumps({"items": [], "message": no_plan(ctx)}, indent=2))
        else:
            print(no_plan(ctx))
        return 0
    views = ctx.views()
    if args.json:
        print(json.dumps({"items": views}, indent=2))
        return 0
    if not views:
        print("No items in %s." % ctx.plan_rel)
        return 0
    width = max(len(v["id"]) for v in views)
    for section in SECTIONS + (OTHER,):
        rows = [v for v in views if v["section"] == section]
        if not rows:
            continue
        print(section)
        for v in rows:
            print("  %s  %s  %s" % (v["id"].ljust(width), v["title"], "[%s]" % status_text(v)))
    if any(v["status"] == "done" and not v["verified"] for v in views):
        print("%s %s" % (UNVERIFIED_MARK, UNVERIFIED))
    return 0


def candidates(views, limit):
    """Open unclaimed items in Now, then stale ones in Now, else open items in Next."""
    out = [dict(v, source="Now") for v in views if v["section"] == "Now" and v["status"] == "open"]
    out += [dict(v, source="Now") for v in views if v["section"] == "Now" and v["status"] == "in progress" and v["stale"]]
    if not out:
        out = [dict(v, source="Next") for v in views if v["section"] == "Next" and v["status"] == "open"]
    return out[:max(limit, 0)]


def cmd_next(ctx, args):
    if not ctx.has_plan():
        if args.json:
            print(json.dumps({"candidates": [], "recommended": None, "message": no_plan(ctx)}, indent=2))
        else:
            print(no_plan(ctx))
        return 0
    found = candidates(ctx.views(), args.limit)
    if args.json:
        print(json.dumps({"candidates": found, "recommended": found[0]["id"] if found else None,
                          "message": "" if found else "Nothing open in Now or Next."}, indent=2))
        return 0
    if not found:
        print("Nothing open in Now or Next.")
        return 0
    print("Next up:")
    for n, v in enumerate(found, 1):
        notes = []
        if v["stale"]:
            notes.append("stale: %s" % describe_claim(v["claim"]))
        if v["source"] == "Next":
            notes.append("from Next")
        if n == 1:
            notes.append("recommended")
        line = "%d. %s %s" % (n, v["id"], v["title"])
        if v["done_means"]:
            line += " · done means: " + v["done_means"]
        print(line + ("  [%s]" % "; ".join(notes) if notes else ""))
    return 0


def check(ctx):
    """(errors, warnings) for the plan file."""
    items = ctx.items()
    errors, warnings = [], []
    seen = {}
    for it in items:
        seen[it.id] = seen.get(it.id, 0) + 1
    for item_id, count in sorted(seen.items()):
        if count > 1:
            errors.append("%s appears %d times." % (item_id, count))
    for it in items:
        if it.checked and not it.evidence:
            warnings.append("%s is checked without evidence (%s)." % (it.id, UNVERIFIED))
        if not it.checked and not it.done_means:
            warnings.append("%s has no \"done means\"." % it.id)
    return errors, warnings


def cmd_check(ctx, args):
    if not ctx.has_plan():
        return fail(no_plan(ctx))
    errors, warnings = check(ctx)
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings}, indent=2))
    else:
        for line in errors:
            print("error: " + line)
        for line in warnings:
            print("warning: " + line)
        if not errors and not warnings:
            print("%s is fine." % ctx.plan_rel)
    return 1 if errors else 0


# ---- done, keep, release ---------------------------------------------------


def evidence_text(evidence, unverified, stamp=None):
    stamp = stamp or gwstatus.stamp_time()
    return "%s (%s)" % (clean(evidence) if evidence else UNVERIFIED, stamp)


def ask_evidence(as_json, item_id, title):
    return ask(as_json, "evidence", "What is the evidence that %s (%s) is done? One line, or mark it unverified." % (item_id, title),
               options=[option("--unverified", "Mark it unverified", "Mark it \"%s\"." % UNVERIFIED)],
               recommended=None, context={"id": item_id, "title": title},
               answer='--evidence "<text>" or --unverified', free_text=True)


def mark_done(ctx, item_id, evidence, unverified, strict=True, stamp=None):
    """Check the item off with evidence, set its progress file to done, release its claim.

    Returns (ok, message). With strict False an item that is already checked is not an error.
    `stamp` is the time written after the evidence (default: now).
    """
    if not ctx.has_plan():
        return False, no_plan(ctx)
    item = next((it for it in ctx.items() if it.id == item_id), None)
    if item is None:
        return False, "No item %s in %s." % (item_id, ctx.plan_rel)
    if item.checked and strict:
        return False, "%s is already done." % item_id
    if not item.checked:
        text = evidence_text(evidence, unverified, stamp)

        def change(line):
            line = re.sub(r"\[ \]", "[x]", line, count=1)
            return with_field(line, "evidence: " + text)

        if not rewrite_item(ctx.plan_path, item_id, change):
            return False, "No item %s in %s." % (item_id, ctx.plan_rel)
    holder = gwclaims.read(ctx.root, item_id)
    if os.path.isfile(gwstatus.task_path(ctx.folder, item_id)):
        rel = gwstatus.stamp_file(ctx.root, ctx.folder, ctx.effective, item_id, state="done")
        gwstatus.emit(ctx.effective, item_id, rel, "stamp")
    gwclaims.release(ctx.root, item_id)
    ctx.emit("task.done", {"id": item_id, "agent": holder.get("agent") if holder else None,
                           "evidence": clean(evidence) if evidence else UNVERIFIED})
    message = "Marked %s done." % item_id
    if holder and gwclaims.read(ctx.root, item_id):  # the claim file could not be removed (a read-only .git, say)
        message += (" Warning: its claim is still in %s, so it still shows as in progress. Remove that file "
                    "or run `plan put-back %s` from a shell that can write there." % (gwclaims.claim_path(ctx.root, item_id), item_id))
    return True, message


def keep_claim(ctx, item_id):
    if gwclaims.touch(ctx.root, item_id) is None:
        return False, "%s is not in progress." % item_id
    return True, "Kept %s in progress." % item_id


def main_root(root):
    """The repository's main working folder (where a plain clone's files are), or `root` without git."""
    code, out, _err = run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    common = out.strip()
    if code != 0 or not common:
        return os.path.realpath(root)
    return os.path.realpath(os.path.dirname(common) if os.path.basename(common) == ".git" else common)


def left_at(ctx, holder):
    """(one line saying where the work stands, the folder it ran in): branch, commit, uncommitted files, worktree."""
    root = ctx.root
    where = (holder or {}).get("worktree") or root
    if not os.path.isdir(where):
        where = root
    parts = ["branch %s at %s" % (gwstatus.current_branch(where) or "none", gwstatus.current_commit(where) or "no commit")]
    files = dirty_paths(ctx, where) if gwstatus.in_git(where) else []
    if files:
        shown = ", ".join(files[:3]) + (" and %d more" % (len(files) - 3) if len(files) > 3 else "")
        parts.append("%d uncommitted file%s (%s)" % (len(files), "" if len(files) == 1 else "s", shown))
    else:
        parts.append("nothing uncommitted")
    if os.path.realpath(where) != main_root(root):
        parts.append("in worktree %s" % os.path.realpath(where))
    return "%s (put back %s)" % ("; ".join(parts), gwstatus.stamp_time()), where


def record_left_at(ctx, item_id, holder):
    """Write `Left at` and State parked into the progress file where the work ran; copy it to the main folder.

    Returns the line, or None when the item has no progress file.
    """
    line, where = left_at(ctx, holder)
    rel = os.path.relpath(gwstatus.task_path(ctx.folder, item_id), ctx.root)
    src = os.path.join(where, rel)
    if not os.path.isfile(src):
        src = os.path.join(ctx.root, rel)
    if not os.path.isfile(src):
        return None
    with open(src, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    gwstatus.set_field(lines, "State", "parked")
    gwstatus.set_field(lines, "Left at", line)
    text = "\n".join(lines)
    gwstatus.write_text(src, text)
    home = os.path.join(main_root(ctx.root), rel)
    if os.path.realpath(home) != os.path.realpath(src):
        gwstatus.write_text(home, text)  # an agent starting from the main folder finds it
    return line


def release_claim(ctx, item_id):
    holder = gwclaims.read(ctx.root, item_id)
    if holder is None:
        return False, "%s is not in progress." % item_id
    line = record_left_at(ctx, item_id, holder)
    gwclaims.release(ctx.root, item_id)
    ctx.emit("task.release", {"id": item_id, "agent": holder.get("agent")})
    where = (" Left at: %s." % line) if line else ""
    return True, "Put %s back: any agent can start it; its progress file keeps what was done.%s" % (item_id, where)


def status_rel(ctx, item_id):
    return gwconfig.display_path(gwstatus.task_path(ctx.folder, item_id), ctx.root)


def ask_save_first(as_json, ctx, item_id, flag):
    """The agent's step before a put-back: bring the progress file up to date."""
    return ask(as_json, "save_first",
               "Before putting %s back, update %s: Done (with evidence), In progress, Open questions and Next action, "
               "so the next agent can continue. Then run the same command again with %s." % (item_id, status_rel(ctx, item_id), flag),
               context={"id": item_id, "progress_file": status_rel(ctx, item_id)}, answer=flag)


def apply_claim_answer(ctx, item_id, answer, evidence, unverified):
    """done | keep | put-back for one item (shared by plan done/keep/put-back, Start and wrap-up)."""
    if answer == "done":
        return mark_done(ctx, item_id, evidence, unverified, strict=False)
    if answer == "keep":
        return keep_claim(ctx, item_id)
    return release_claim(ctx, item_id)


# ---- done --verify ---------------------------------------------------------


def verify_timeout(ctx):
    """`plan.verifyTimeout` ("90s", "30m", "1h") in seconds; 30 minutes when it cannot be read."""
    m = VERIFY_TIMEOUT_RE.match(ctx.effective.get("plan.verifyTimeout") or "")
    if not m:
        return VERIFY_TIMEOUT_DEFAULT
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600}[m.group(2)]


def output_tail(raw, count=VERIFY_TAIL_LINES):
    """The last `count` non-blank-ended lines of command output: colors removed, each line clipped."""
    text = ANSI_RE.sub("", raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return [ln if len(ln) <= VERIFY_LINE_MAX else ln[:VERIFY_LINE_MAX - 3] + "..." for ln in lines[-count:]]


def stop_group(proc):
    """Kill the command's whole process group (the shell and what it started)."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (OSError, ProcessLookupError):
        pass


def run_verify(root, command, timeout):
    """Run `command` in a shell from `root`, stdout and stderr together. The command text comes only
    from the caller. Returns a dict: passed, exit_code (None when none), seconds, timed_out, error, output (bytes)."""
    result = {"passed": False, "exit_code": None, "seconds": 0.0, "timed_out": False, "error": None, "output": b""}
    started = time.monotonic()
    try:
        proc = subprocess.Popen(command, shell=True, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"))
    except OSError as e:
        result["error"] = "could not start: %s" % e
        return result
    try:
        result["output"], _ = proc.communicate(timeout=timeout)
        result["exit_code"] = proc.returncode
        result["passed"] = proc.returncode == 0
    except subprocess.TimeoutExpired as e:
        result["timed_out"] = True
        stop_group(proc)
        try:
            result["output"], _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            result["output"] = e.output or b""
        proc.poll()
    result["seconds"] = time.monotonic() - started
    return result


def format_seconds(seconds):
    return "%.1f s" % seconds if seconds < 10 else "%d s" % round(seconds)


def short_command(command):
    text = clean(command)
    return text if len(text) <= VERIFY_CMD_MAX else text[:VERIFY_CMD_MAX - 3] + "..."


def failure_reason(result, timeout):
    if result["error"]:
        return result["error"]
    if result["timed_out"]:
        return "timed out after %s" % format_seconds(timeout)
    return "exit %s" % result["exit_code"]


def journal_failure(ctx, item_id, command, result, reason, stamp, tail):
    """Append the failed verify to the item's journal: one line, then the output tail indented 4 spaces.
    The first line has no commit word, so journal.last_commit never reads it as a facts line."""
    path = os.path.join(ctx.folder, "journal", item_id + ".md")
    head = "- %s verify failed (%s, %s): %s" % (stamp, reason, format_seconds(result["seconds"]), short_command(command))
    body = ["    " + ln for ln in tail] if tail else ["    (no output)"]
    entry = gwredact.clean("\n".join([head] + body), os.path.basename(path))
    try:
        gwjournal.append_line(path, item_id, entry)
    except OSError as e:
        print("warning: could not write %s: %s" % (gwconfig.display_path(path, ctx.root), e), file=sys.stderr)
        return None
    return gwconfig.display_path(path, ctx.root)


def done_verified(ctx, args):
    """`plan done <id> --verify "<cmd>"`: run the command; a pass ticks the item as confirmed,
    a fail leaves PLAN.md alone and records the output tail in the journal."""
    if not ctx.has_plan():
        return fail(no_plan(ctx))
    item = next((it for it in ctx.items() if it.id == args.id), None)
    if item is None:
        return fail("No item %s in %s." % (args.id, ctx.plan_rel))
    if item.checked:
        return fail("%s is already done." % args.id)
    command = args.verify
    timeout = verify_timeout(ctx)
    result = run_verify(ctx.root, command, timeout)
    stamp = gwstatus.stamp_time()
    info = {"command": command, "passed": result["passed"], "exit_code": result["exit_code"],
            "seconds": round(result["seconds"], 1), "timed_out": result["timed_out"], "time": stamp}
    if result["passed"]:
        evidence = "%s %s passed in %s" % (VERIFIED_PREFIX, short_command(command), format_seconds(result["seconds"]))
        ok, message = mark_done(ctx, args.id, evidence, False, stamp=stamp)
        if ok:
            gwstatus.set_note(ctx.folder, args.id, "confirmed", stamp)
            message = "%s Verified: %s passed in %s." % (message, short_command(command), format_seconds(result["seconds"]))
        return report(args, ok, message, {"id": args.id, "done": ok, "verify": info})
    reason = failure_reason(result, timeout)
    tail = output_tail(result["output"])
    info.update(error=result["error"], output_tail=tail)
    journal = journal_failure(ctx, args.id, command, result, reason, stamp, tail)
    message = "Verify failed (%s, %s): %s. %s stays open." % (reason, format_seconds(result["seconds"]), short_command(command), args.id)
    if journal:
        message += " Output (last %d lines at most) is in %s." % (VERIFY_TAIL_LINES, journal)
    if args.json:
        print(json.dumps({"id": args.id, "done": False, "verify": dict(info, journal=journal), "message": message}, indent=2))
    else:
        print(message, file=sys.stderr)
        for line in tail:
            print("    " + line, file=sys.stderr)
    return 1


def cmd_done(ctx, args):
    if args.verify is not None:
        if args.evidence or args.unverified:
            return fail("--verify cannot be combined with --evidence or --unverified. "
                        "Use --verify when a command can prove %s is done; use --evidence for what no command can check." % args.id)
        if not args.verify.strip():
            return fail("--verify needs a command to run.")
        return done_verified(ctx, args)
    if not (args.evidence or args.unverified):
        item = next((it for it in ctx.items() if it.id == args.id), None)
        if item is None:
            return fail("No item %s in %s." % (args.id, ctx.plan_rel))
        return ask_evidence(args.json, args.id, item.title)
    ok, message = mark_done(ctx, args.id, args.evidence, args.unverified)
    return report(args, ok, message, {"id": args.id, "done": ok})


def cmd_keep(ctx, args):
    ok, message = keep_claim(ctx, args.id)
    return report(args, ok, message, {"id": args.id, "kept": ok})


def cmd_release(ctx, args):
    if not args.saved and gwclaims.read(ctx.root, args.id) is not None and os.path.isfile(gwstatus.task_path(ctx.folder, args.id)):
        return ask_save_first(args.json, ctx, args.id, "--saved")
    ok, message = release_claim(ctx, args.id)
    return report(args, ok, message, {"id": args.id, "put_back": ok})


def report(args, ok, message, data):
    if not ok:
        return fail(message)
    if getattr(args, "json", False):
        print(json.dumps(dict(data, message=message), indent=2))
    else:
        print(message)
    return 0


# ---- git helpers for Start -------------------------------------------------


def run_git(root, *args):
    """(return code, stdout, stderr)."""
    try:
        out = subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return out.returncode, out.stdout, out.stderr.strip()


def is_worktree(root, path):
    """True when `path` is one of this repository's git worktrees."""
    code, out, _err = run_git(root, "worktree", "list", "--porcelain")
    target = os.path.realpath(path)
    return code == 0 and any(os.path.realpath(l[len("worktree "):]) == target
                             for l in out.splitlines() if l.startswith("worktree "))


def branch_exists(root, name):
    return run_git(root, "show-ref", "--verify", "--quiet", "refs/heads/" + name)[0] == 0


def default_branch(root):
    """origin's default branch, else main, else master, else "HEAD"."""
    code, out, _err = run_git(root, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    if code == 0 and out.strip():
        name = out.strip()
        local = name.split("/", 1)[1] if "/" in name else name
        return local if branch_exists(root, local) else name
    for name in ("main", "master"):
        if branch_exists(root, name):
            return name
    return "HEAD"


def item_branch(item_id, title):
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:MAX_SLUG].strip("-")
    return item_id.lower() + ("-" + slug if slug else "")


def dirty_paths(ctx, folder=None):
    """Changed or new paths that are not whatsnext's own files (the progress folder, the plan, .whatsnext/)."""
    code, out, _err = run_git(folder or ctx.root, "status", "--porcelain", "-z", "-uall")
    if code != 0:
        return []
    ignore = [ctx.effective.get("paths.progress").rstrip("/") + "/", ".whatsnext/"]
    entries = out.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            i += 1  # the old name follows
        path = entry[3:]
        if path == ctx.plan_rel or any(path.startswith(p) for p in ignore):
            continue
        paths.append(path)
    return paths


def save_always(ctx, choice):
    """Save plan.branchOnStart in .whatsnext/config.local.json, keeping the other keys."""
    path = os.path.join(ctx.root, ".whatsnext", "config.local.json")
    data = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as e:
            print("warning: not saving plan.branchOnStart: cannot read %s: %s" % (gwconfig.display_path(path, ctx.root), e),
                  file=sys.stderr)
            return False
    plan = data.get("plan")
    if not isinstance(plan, dict):
        plan = data["plan"] = {}
    plan["branchOnStart"] = choice
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return True


# ---- Start (ADR-0002) ------------------------------------------------------


def cmd_start(ctx, args):
    as_json = args.json
    if not ctx.has_plan():
        return fail(no_plan(ctx))
    item = next((it for it in ctx.items() if it.id == args.id), None)
    if item is None:
        return fail("No item %s in %s." % (args.id, ctx.plan_rel))
    tasks = ctx.tasks()
    existing = gwclaims.read(ctx.root, item.id)
    view = ctx.view(item, tasks.get(item.id), existing)
    # 1. The item is open, not blocked and not done.
    if view["status"] == "done":
        return fail("%s is already done." % item.id)
    if view["status"] == "blocked":
        return fail("%s is blocked. The blocker is in %s." % (
            item.id, gwconfig.display_path(gwstatus.task_path(ctx.folder, item.id), ctx.root)))
    agent = agent_name(args)
    ours = gwclaims.is_ours(existing, agent, ctx.root)
    # 2. In progress with someone else.
    if existing and not ours and not args.takeover:
        info = view["claim"]
        idle = " (idle since %s)" % info["idle_short"] if info["idle_short"] != "unknown" else ""
        return ask(as_json, "takeover", "%s has had %s in progress since %s%s. Take it over?" % (
            info["agent"], item.id, info["since_short"], idle),
            options=[option("yes", "Take it over", "Take it over from %s." % info["agent"]),
                     option("no", "Leave it", "Leave it with %s and pick another item." % info["agent"])],
            recommended="yes" if info["stale"] else "no",
            context={"id": item.id, "title": item.title, "claim": info}, answer="--takeover (for yes)")
    # 3. No "done means".
    done_means = clean(args.done_means) or item.done_means
    if not done_means:
        return ask(as_json, "done_means", "What does done mean for %s (%s)? One line." % (item.id, item.title),
                   context={"id": item.id, "title": item.title}, answer='--done-means "<text>"', free_text=True)
    # 4 and 5 apply to a new Start; an item this agent already holds is being resumed.
    dirty, current = [], None
    if not ours:
        # 4. Uncommitted changes from other work.
        dirty = dirty_paths(ctx) if gwstatus.in_git(ctx.root) else []
        if dirty and not args.dirty:
            shown = ", ".join(dirty[:5]) + (" and %d more" % (len(dirty) - 5) if len(dirty) > 5 else "")
            return ask(as_json, "uncommitted", "There are %d uncommitted change%s from other work (%s). What should happen to %s before %s starts?" % (
                len(dirty), "" if len(dirty) == 1 else "s", shown, "it" if len(dirty) == 1 else "them", item.id),
                options=[option("commit", "Commit them first", "Commit them first (this script never commits; the agent does)."),
                         option("stash", "Stash them", "Stash them, new files included, and bring them back later with git stash pop."),
                         option("carry-on", "Carry on", "Leave them in place and start anyway.")],
                recommended="commit", context={"id": item.id, "files": dirty}, answer="--dirty commit|stash|carry-on")
        if dirty and args.dirty == "commit":
            return ask(as_json, "commit_first", "Commit the uncommitted changes first (%d file%s), then run the same command again." % (
                len(dirty), "" if len(dirty) == 1 else "s"), context={"id": item.id, "files": dirty})
        # 5. Another item in progress from this worktree.
        mine = gwclaims.worktree_root(ctx.root)
        others = [c for i, c in sorted(gwclaims.read_all(ctx.root).items()) if i != item.id and c.get("worktree") == mine]
        if others:
            current = others[0]
            cur_item = next((it for it in ctx.items() if it.id == current["id"]), None)
            cur_title = cur_item.title if cur_item else ""
            task = tasks.get(current["id"])
            unfinished = bool(task is not None and task.section("In progress"))
            if not args.current:
                info = ctx.view(cur_item, task, current)["claim"] if cur_item else {"agent": current.get("agent")}
                return ask(as_json, "current_item", "%s is still in progress from this folder. Mark it done, keep working on it, or put it back?" % current["id"],
                           options=[option("done", "Mark it done", "Mark %s done (with one line of evidence)." % current["id"]),
                                    option("keep", "Keep working on it", "Keep %s in progress; its progress file stays as it is." % current["id"]),
                                    option("put-back", "Put it back", "Put %s back for any agent to start; its progress file keeps what was done." % current["id"])],
                           recommended="keep" if unfinished else "done",
                           context={"id": current["id"], "title": cur_title, "claim": info, "has_unfinished_work": unfinished},
                           answer="--current done|keep|put-back (done also needs --evidence \"<text>\" or --unverified)")
            if args.current == "done" and not (args.evidence or args.unverified):
                return ask_evidence(as_json, current["id"], cur_title)
            if args.current == "put-back" and not args.saved and task is not None:
                return ask_save_first(as_json, ctx, current["id"], "--saved")
    # Every check passed. Side effects start here.
    if dirty and args.dirty == "stash":
        code, _out, err = run_git(ctx.root, "stash", "push", "-u", "-m", "whatsnext: before " + item.id, "--", *dirty)
        if code != 0:
            return fail("Could not stash the changes: %s" % err)
    if current is not None:
        ok, message = apply_claim_answer(ctx, current["id"], args.current, args.evidence, args.unverified)
        if not ok:
            return fail(message)
    if args.done_means and not item.done_means:
        text = done_means
        rewrite_item(ctx.plan_path, item.id, lambda line: with_field(line, "done means: " + text))
    mine_claim, other = gwclaims.claim(ctx.root, item.id, agent, session=args.session,
                                       branch=gwstatus.current_branch(ctx.root), takeover=bool(existing and not ours))
    if mine_claim is None:
        return fail("%s was just taken by %s. Pick another item, or ask the user to take it over." % (
            item.id, (other or {}).get("agent") or "someone else"))
    if not ours:
        ctx.emit("task.start", {"id": item.id, "agent": agent, "branch": gwstatus.current_branch(ctx.root)})
    earlier = earlier_work(ctx, item.id)
    status_rel = start_status_file(ctx, item, done_means, agent, keep_parked=bool(earlier))
    # Branch.
    result = start_branch(ctx, args, item, agent, status_rel, earlier)
    if isinstance(result, int):
        return result
    if earlier and result["action"] != "worktree":
        gwstatus.stamp_file(ctx.root, ctx.folder, ctx.effective, item.id, state="active")
    info = {"started": True, "id": item.id, "title": item.title, "done_means": done_means, "agent": agent,
            "progress_file": result["progress_file"], "branch": result["branch"], "branch_action": result["action"],
            "worktree": result["worktree"], "earlier_work": earlier, "next_step": NEXT_STEP}
    if as_json:
        print(json.dumps(info, indent=2))
        return 0
    print("Started %s: %s" % (item.id, item.title))
    print("Done means: " + done_means)
    print("Progress file: " + info["progress_file"])
    if earlier:
        print("Earlier work: %s. Read the progress file before changing anything." % earlier)
    if info["worktree"]:
        print("Worktree: %s (branch %s). Tell the user to open this folder and continue there." % (info["worktree"], info["branch"]))
    elif info["branch"]:
        print("Branch: %s%s" % (info["branch"], " (new)" if info["branch_action"] == "branch" else ""))
    print("Next: " + NEXT_STEP)
    return 0


def earlier_work(ctx, item_id):
    """The `Left at` line of an item that was put back (State parked), else None."""
    path = gwstatus.task_path(ctx.folder, item_id)
    if not os.path.isfile(path):
        return None
    fields = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f.read().split("\n"):
            if raw.startswith("## "):
                break
            m = gwstatus.FIELD_RE.match(raw.rstrip("\r"))
            if m:
                fields[m.group(1).strip().lower()] = m.group(2)
    return fields.get("left at") if fields.get("state", "").split(" ")[0] == "parked" else None


def start_status_file(ctx, item, done_means, agent, keep_parked=False):
    """Create the item's progress file, or set it active again (a put-back one only once Start is done)."""
    path = gwstatus.task_path(ctx.folder, item.id)
    if os.path.isfile(path):
        rel = gwstatus.stamp_file(ctx.root, ctx.folder, ctx.effective, item.id, state=None if keep_parked else "active",
                                  agent=agent)
        gwstatus.emit(ctx.effective, item.id, rel, "stamp")
        return rel
    text = gwstatus.TEMPLATE % {
        "id": item.id, "title": item.title, "agent": agent, "branch": gwstatus.current_branch(ctx.root) or gwstatus.NONE,
        "commit": gwstatus.current_commit(ctx.root) or gwstatus.NONE, "updated": gwstatus.stamp_time(),
        "placeholder": FIRST_STEP}
    text = text.replace("## Goal\n\n## Done", "## Goal\n\n%s\nDone means: %s\n\n## Done" % (item.title, done_means), 1)
    gwstatus.write_text(path, text)
    rel = gwconfig.display_path(path, ctx.root)
    gwstatus.emit(ctx.effective, item.id, rel, "new")
    return rel


def start_branch(ctx, args, item, agent, status_rel, earlier=None):
    """Step 9. Returns a result dict, or an exit code (4 when the user must choose)."""
    root = ctx.root
    result = {"progress_file": status_rel, "branch": gwstatus.current_branch(root), "action": "skipped", "worktree": None}
    if not gwstatus.in_git(root):
        return result
    name = item_branch(item.id, item.title)
    current = gwstatus.current_branch(root)
    if current == name:
        if args.always and args.branch:
            save_always(ctx, args.branch)
        return result
    choice = args.branch or (ctx.effective.get("plan.branchOnStart") if ctx.effective.get("plan.branchOnStart") != "ask" else None)
    base = default_branch(root)
    if not choice:
        others = [c for i, c in gwclaims.read_all(root).items()
                  if i != item.id and c.get("worktree") == gwclaims.worktree_root(root) and c.get("agent") != agent]
        recommended = "branch" if current == base else "worktree" if others else "stay"
        wt = worktree_path(root, item.id)
        has_branch, has_wt = branch_exists(root, name), is_worktree(root, wt)
        if earlier and has_wt:
            recommended = "worktree"
        elif earlier and has_branch:
            recommended = "branch"
        branch_text = ("Branch %s, where the earlier work is." % name) if has_branch else "New branch %s from %s." % (name, base)
        wt_text = ("The existing worktree at %s, where the earlier work is." % wt) if has_wt else (
            "New worktree at %s on branch %s." % (wt, name))
        return ask(args.json, "branch", "Where should %s work happen? It is already in progress for you." % item.id,
                   options=[option("branch", ("Branch %s" if has_branch else "New branch %s") % name, branch_text),
                            option("stay", "Stay on %s" % current, "Stay on the current branch, %s." % current),
                            option("worktree", "Existing worktree" if has_wt else "New worktree", wt_text)],
                   recommended=recommended, context={"id": item.id, "branch_name": name, "current": current, "default": base,
                                                     "worktree_path": wt, "claimed": True, "earlier_work": earlier},
                   answer="--branch branch|stay|worktree [--always]")
    if args.always and args.branch:
        save_always(ctx, args.branch)
    if choice == "stay":
        result["action"] = "stay"
        gwstatus.stamp_file(root, ctx.folder, ctx.effective, item.id)
        return result
    has_commit = gwstatus.current_commit(root) is not None
    if choice == "branch":
        if branch_exists(root, name):
            code, _o, err = run_git(root, "switch", name)
        elif has_commit:
            code, _o, err = run_git(root, "switch", "-c", name, base)
        else:
            code, _o, err = run_git(root, "switch", "-c", name)
        if code != 0:
            return fail("Could not switch to branch %s: %s" % (name, err))
        result.update(action="branch", branch=name)
        gwstatus.stamp_file(root, ctx.folder, ctx.effective, item.id)
        gwclaims.update(root, item.id, branch=name)
        return result
    path = worktree_path(root, item.id)  # worktree
    if is_worktree(root, path):  # the earlier work's worktree: continue there
        new_root = os.path.realpath(path)
        new_ctx = Ctx(new_root, gwconfig.load(new_root))
        home = gwstatus.task_path(ctx.folder, item.id)
        there = gwstatus.task_path(new_ctx.folder, item.id)
        if os.path.isfile(home) and os.path.realpath(home) != os.path.realpath(there):
            shutil.copyfile(home, there)  # the copy put-back left in the main folder is the newer one
        gwstatus.stamp_file(new_root, new_ctx.folder, new_ctx.effective, item.id, state="active", agent=agent)
        gwclaims.update(root, item.id, branch=gwstatus.current_branch(new_root) or name, worktree=new_root)
        result.update(action="worktree", branch=gwstatus.current_branch(new_root) or name, worktree=new_root)
        result["progress_file"] = gwconfig.display_path(there, new_root)
        return result
    if os.path.exists(path):
        return fail("Cannot create the worktree: %s already exists." % path)
    if branch_exists(root, name):
        code, _o, err = run_git(root, "worktree", "add", path, name)
    else:
        code, _o, err = run_git(root, "worktree", "add", path, "-b", name, base)
    if code != 0:
        return fail("Could not create the worktree: %s" % err)
    new_root = os.path.realpath(path)
    move_status_file(ctx, new_root, item.id)
    new_ctx = Ctx(new_root, gwconfig.load(new_root))
    gwstatus.stamp_file(new_root, new_ctx.folder, new_ctx.effective, item.id)
    gwclaims.update(root, item.id, branch=name, worktree=new_root)
    result.update(action="worktree", branch=name, worktree=new_root)
    result["progress_file"] = gwconfig.display_path(gwstatus.task_path(new_ctx.folder, item.id), new_root)
    return result


def worktree_path(root, item_id):
    return os.path.join(os.path.dirname(root), "%s-%s" % (os.path.basename(root), item_id.lower()))


def move_status_file(ctx, new_root, item_id):
    """Give a new worktree the progress file. The copy in the old folder goes when this Start created it (untracked)."""
    src = gwstatus.task_path(ctx.folder, item_id)
    rel = os.path.relpath(src, ctx.root)
    dst = os.path.join(new_root, rel)
    if os.path.isfile(dst) or not os.path.isfile(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    tracked = run_git(ctx.root, "ls-files", "--error-unmatch", "--", rel)[0] == 0
    if not tracked:
        os.remove(src)


# ---- command line ----------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(prog="whatsnext plan", description="The plan checklist, Start, and items in progress.")
    sub = parser.add_subparsers(dest="action")
    p = sub.add_parser("list", help="all items with their status and who has them in progress")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("next", help="what to work on next")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=3)
    p = sub.add_parser("check", help="find items without evidence or done means, and duplicate ids")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("start", help="mark an item in progress and start work (exit 4: the agent must ask the user)")
    p.add_argument("id")
    p.add_argument("--agent", help="default: $WHATSNEXT_AGENT, then $GROUNDWORK_AGENT, else unknown")
    p.add_argument("--session")
    p.add_argument("--takeover", action="store_true", help="take over an item someone else has in progress")
    p.add_argument("--done-means", help="done means, when the item has none")
    p.add_argument("--dirty", choices=("commit", "stash", "carry-on"), help="what to do with uncommitted changes")
    p.add_argument("--current", choices=("done", "keep", "put-back"), help="what to do with the item already in progress here")
    p.add_argument("--evidence", help="evidence for --current done")
    p.add_argument("--saved", action="store_true", help="with --current put-back: its progress file is up to date")
    p.add_argument("--unverified", action="store_true", help="mark --current done as checked by a person, not verified")
    p.add_argument("--branch", choices=BRANCH_CHOICES, help="where the work runs")
    p.add_argument("--always", action="store_true", help="with --branch: save the choice as plan.branchOnStart")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("done", help="mark an item done with a passing command (--verify) or a person's evidence")
    p.add_argument("id")
    p.add_argument("--evidence", help="one line of evidence no command can check; the item shows as done* (not verified)")
    p.add_argument("--unverified", action="store_true")
    p.add_argument("--verify", metavar="CMD", help="run CMD from the project root; exit 0 marks the item done and confirmed, anything else leaves it open (not combinable with --evidence)")
    p.add_argument("--json", action="store_true")
    for name, text in (("keep", "keep an item in progress (resets its idle time)"), ("put-back", "put an item back for any agent to start")):
        p = sub.add_parser(name, help=text)
        p.add_argument("id")
        p.add_argument("--json", action="store_true")
        if name == "put-back":
            p.add_argument("--saved", action="store_true", help="its progress file is up to date (asked for first)")
    return parser


def run(argv, cwd=None):
    args = build_parser().parse_args(argv)
    ctx = Ctx.load(cwd)
    if args.action is None:
        args.action, args.json = "list", False
    handler = {"list": cmd_list, "next": cmd_next, "check": cmd_check, "start": cmd_start, "done": cmd_done,
               "keep": cmd_keep, "put-back": cmd_release}[args.action]
    return handler(ctx, args)
