"""Re-check a handoff note's `Check:` lines (P-87, ADR-0030): VERIFIED, STALE or BROKEN.

`status` runs only the git facts (HEAD, branch, clean). A `run` check runs only from `handoff verify`, which the
person starts. No model call.
"""

import re

from . import journal as gwjournal
from . import packet as gwpacket
from . import status as gwstatus

CHECK_RE = re.compile(r"^check\s*:\s*(.+?)\s*$", re.IGNORECASE)
HEAD_RE = re.compile(r"^head\s*==\s*([0-9a-fA-F]{4,40})$", re.IGNORECASE)
BRANCH_RE = re.compile(r"^branch\s*==\s*(\S+)$", re.IGNORECASE)
CLEAN_RE = re.compile(r"^clean$", re.IGNORECASE)
RUN_RE = re.compile(r"^run\s+`(.+)`$", re.IGNORECASE)
BROKEN_CODES = (126, 127)

VERIFIED, STALE, BROKEN, NOT_RUN = "VERIFIED", "STALE", "BROKEN", "not run"


def checks(body):
    """Every `Check:` line in the note's State section, outside code fences and not indented."""
    section = gwstatus.get_section(body.split("\n"), "State")
    found, fenced = [], False
    for line in section.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        m = None if fenced else CHECK_RE.match(line)
        if m:
            found.append(m.group(1).strip())
    return found


def run_commands(body):
    """The commands of every `Check: run` line, for a person to read before they allow them."""
    return [m.group(1) for m in (RUN_RE.match(t) for t in checks(body)) if m]


def git_value(root, *args):
    code, out = gwstatus.git(root, *args)
    return out.strip() if code == 0 else None


def check_one(root, text, run=None):
    """{'check', 'verdict', 'detail'}. `run(command)` returns run_verify's dict; without it a run check is not run."""
    out = {"check": text, "verdict": BROKEN, "detail": ""}
    m = HEAD_RE.match(text)
    if m:
        head = git_value(root, "rev-parse", "HEAD")
        if head is None:
            out["detail"] = "git could not read HEAD"
        else:
            ok = head.lower().startswith(m.group(1).lower())
            out.update(verdict=VERIFIED if ok else STALE, detail="HEAD is %s" % head[:7])
        return out
    m = BRANCH_RE.match(text)
    if m:
        branch = gwstatus.current_branch(root)
        if not branch:
            out["detail"] = "no current branch"
        else:
            out.update(verdict=VERIFIED if branch == m.group(1) else STALE, detail="branch is %s" % branch)
        return out
    if CLEAN_RE.match(text):
        dirty = git_value(root, "status", "--porcelain")
        if dirty is None:
            out["detail"] = "git could not read the status"
        else:
            n = len([ln for ln in dirty.splitlines() if ln.strip()])
            out.update(verdict=STALE if n else VERIFIED, detail="%d uncommitted file%s" % (n, "" if n == 1 else "s"))
        return out
    m = RUN_RE.match(text)
    if m:
        if run is None:
            out.update(verdict=NOT_RUN, detail="run `whatsnext handoff verify` to run it")
            return out
        result = run(m.group(1))
        out.update(verdict=verdict_of(result), detail=reason_of(result))
        return out
    out["detail"] = "unknown check form"
    return out


def verdict_of(result):
    if result.get("passed"):
        return VERIFIED
    return BROKEN if is_broken(result) else STALE


def is_broken(result):
    """True when the command could not tell: not started, not runnable or not found, or timed out."""
    return bool(result.get("error") or result.get("timed_out") or result.get("exit_code") in BROKEN_CODES)


def reason_of(result):
    if result.get("error"):
        return result["error"]
    if result.get("timed_out"):
        return "timed out"
    return "exit %s" % result.get("exit_code")


def check_all(root, body, run=None):
    return [check_one(root, text, run) for text in checks(body)]


def line(results):
    """One status line: counts per verdict, then each check that is not VERIFIED."""
    if not results:
        return ""
    counts = [(v, sum(1 for r in results if r["verdict"] == v)) for v in (VERIFIED, STALE, BROKEN, NOT_RUN)]
    head = ", ".join("%d %s" % (n, v) for v, n in counts if n)
    def safe(text):  # the note may come from a commit: no control characters, short
        return gwpacket.clip(gwpacket.clean(text), 120)
    bad = ["%s: %s (%s)" % (r["verdict"], safe(r["check"]), safe(r["detail"])) for r in results if r["verdict"] != VERIFIED]
    return "Handoff checks: " + head + ("; " + "; ".join(bad) if bad else "")
