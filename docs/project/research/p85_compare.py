#!/usr/bin/env python3
"""P-85 step 1 (measurement): compare each saved compact summary with the handoff note in force at compact time.

Mechanical parts (this script does them): find the 17 saved summaries, read their timestamps and task, list every
handoff-note version (git history of docs/project/HANDOFF.md, the current file, docs/project/handoffs/*.md), pair
each summary with the latest note written before the compact (same session first), measure bytes, split the summary
into sentence-level units, and compute a lexical cross-check (share of the summary's word 4-grams that also occur in
the note).

Judgment parts (recorded by hand, below in FACTS and JUDGE): which facts a note holds, which of them the summary
restates (overlap), which it contradicts (conflict). Every hand judgment is tied to a regex that must match the
summary text; the script stops with an error when one does not, so the record cannot drift from the data.

Run from anywhere:  python3 docs/project/research/p85_compare.py
Standard library only, Python 3.9+. Read-only: it writes nothing.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SESSIONS = os.path.join(ROOT, ".whatsnext", "sessions")
HANDOFF = "docs/project/HANDOFF.md"
ARCHIVE = os.path.join(ROOT, "docs", "project", "handoffs")

# ---------------------------------------------------------------------------------------------------------------
# Hand-recorded judgment, part 1: the facts each handoff note holds (id: (category, short text)).
# Categories: goal, next, state, tests, files, decisions, constraints, open (questions and blockers), deadend.
# ---------------------------------------------------------------------------------------------------------------
FACTS = {
    "H1": {  # git f2790a3, written 2026-11-06T22:56Z, session 2230ec21, task none
        "G1": ("goal", "ship the release: compact safety net, handoff checks, multi-agent fixes"),
        "G2": ("goal", "all 31 plan items are built"),
        "N1": ("next", "try the three unverified hooks in a real session"),
        "N2": ("next", "run `doctor`"),
        "N3": ("next", "verify: 408 tests pass and doctor shows no gap"),
        "S1": ("state", "all 31 items done and verified"),
        "S2": ("state", "branch merged into local main 1285a38, 39 commits ahead, not pushed"),
        "S3": ("state", "PR #1 is open"),
        "T1": ("tests", "408 tests pass"),
        "T2": ("tests", "soak test: 0 double claims in 60 runs"),
        "F1": ("files", "compact: hook.py, compact.py, wrapup.py"),
        "F2": ("files", "handoff: wrapup.py, crosscheck.py, handoffverify.py"),
        "F3": ("files", "plan: plan.py, util.py"),
        "F4": ("files", "health and claims: doctor.py, claims.py, soak test"),
        "D1": ("decisions", "ADR-0011 to ADR-0014 accepted 2026-11-06"),
        "C1": ("constraints", "standard library only, Python 3.9+"),
        "C2": ("constraints", "do not push main or create a remote without asking"),
        "C3": ("constraints", "keep AGENTS.md under 30 lines"),
        "C4": ("constraints", "run the unittest suite before reporting done"),
        "C5": ("constraints", "never copy code from other tools"),
        "C6": ("constraints", "run a suite with its exit code checked, not through a pipe"),
        "Q1": ("open", "push main or merge PR #1?"),
        "Q2": ("open", "hooks not run in a real agent (Codex PreToolUse, UserPromptSubmit, PostCompact; Claude warning)"),
        "Q3": ("open", "`plan check` is noisy with stale-verify warnings"),
    },
    "H3": {  # git 8b1b172 = archive 20261107T0625Z-none.md, written 2026-11-07T06:25Z, session 869b255f, task none
        "G1": ("goal", "after a compact the resume note repeats the latest request and open work (ADR-0015)"),
        "N1": ("next", "finish P-39: claude --plugin-dir ., /compact, check the note shows 'Before the compact the user asked'"),
        "N2": ("next", "verify: 418 tests pass"),
        "N3": ("next", "if it fails run tests.test_hook -k compact_carry"),
        "S1": ("state", "built and committed locally on branch p-32-next-shows-handoff, not pushed"),
        "S2": ("state", "not seen in a real Claude Code session yet"),
        "T1": ("tests", "418 tests pass"),
        "F1": ("files", "PreCompact saves `carry` (~420 chars) in compact.json (hook.py, wrapup.py)"),
        "F2": ("files", "packet.py compacted_text appends it"),
        "F3": ("files", "setting note.carryAfterCompact"),
        "F4": ("files", "3 tests, GUIDE paragraph, ADR-0015"),
        "D1": ("decisions", "ADR-0015 accepted by the user 2026-11-07"),
        "D2": ("decisions", "not built: 15-minute expiry, 5-bullet cap, summary-dedupe check"),
        "D3": ("decisions", "carry is 420 characters, not 2,000"),
        "C1": ("constraints", "standard library only, Python 3.9+"),
        "C2": ("constraints", "do not push or create a remote without asking"),
        "C3": ("constraints", "do not name other plugins in code or public docs"),
        "C4": ("constraints", "run the full suite before reporting done (about 11 minutes)"),
        "Q1": ("open", "unrelated P-39 progress edits and tsconfig.json left uncommitted"),
    },
    "H_a09": {  # git 0f217bf = archive 20261110T2159Z-P-61.md, written 2026-11-10T21:59Z, session a09a001d, task P-61
        "G1": ("goal", "finish P-61: `progress pr-body <id>` prints a PR description, no model call"),
        "N1": ("next", "ask the user to approve committing P-61"),
        "N2": ("next", "then commit and run `plan done P-61 --verify` (reuses the saved run)"),
        "N3": ("next", "commit the done mark, fast-forward main"),
        "N4": ("next", "verify: PLAN.md shows P-61 checked with '(reused run of 2026-11-10T21:5'"),
        "N5": ("next", "if it fails: a changed file breaks reuse; rerun (~7 min) or `plan test P-61`"),
        "S1": ("state", "P-61 built, not committed, on its own branch"),
        "S2": ("state", "main at 15e90e1 with P-57, P-58, P-59, P-60, P-66 done and merged locally"),
        "S3": ("state", "nothing is pushed"),
        "T1": ("tests", "`plan test P-61` passed: 660 tests in 407 s, saved for reuse"),
        "F1": ("files", "wn/prbody.py (new), wn/status.py"),
        "F2": ("files", "tests/test_prbody.py (11 tests), SKILL.md row"),
        "F3": ("files", "P-57, P-58, P-59, P-60, P-66 on main (what each added)"),
        "F4": ("files", "9b488fb, dfbf33f cherry-picked from p-32"),
        "F5": ("files", "tsconfig.json deleted"),
        "D1": ("decisions", "ADR-0022 human review accepted"),
        "D2": ("decisions", "ADR-0023 reuse a passing run accepted"),
        "D3": ("decisions", "ADR-0021 added to the decisions index"),
        "C1": ("constraints", "local only: no push, no remote without asking"),
        "C2": ("constraints", "standard library only, Python 3.9+"),
        "C3": ("constraints", "ask before each commit and merge"),
        "C4": ("constraints", "each item on its own branch from main, ff-only merge"),
        "C5": ("constraints", "leave progress/journal/P-52.md uncommitted"),
        "C6": ("constraints", "show the plan steps in the approval question"),
        "Q1": ("open", "user has not answered 'Commit P-61, mark done, merge?'"),
        "Q2": ("open", "old: rightsize CLI welcome table wraps; star ask uncommitted in rightsize"),
        "Q3": ("open", "after P-61, Now and Next are empty"),
        "X1": ("deadend", "matching saved runs on the commit: dropped"),
        "X2": ("deadend", "`git branch --merged` alone: dropped, `git cherry` used too"),
    },
    "H_c917": {  # git dccf50e = archive 20261116T2114Z-none.md, written 2026-11-16T21:14Z, session c917f1f8, task none
        "G1": ("goal", "make whatsnext work in any coding agent (ADR-0027)"),
        "N1": ("next", "pick the next item: `wn status`, start the recommended one (P-79; also P-72, P-73)"),
        "N2": ("next", "verify: `wn plan list` shows the item in progress"),
        "N3": ("next", "if it fails: `wn plan check`"),
        "S1": ("state", "P-75, P-76, P-77, P-78, P-82 done and merged into main (last merge 0d07568)"),
        "S2": ("state", "P-76, P-77, P-82 verified; P-75 and P-78 done* (live runs)"),
        "S3": ("state", "nothing pushed"),
        "T1": ("tests", "last full suite OK (448 s)"),
        "F1": ("files", "584d5e4 P-75 hook-free mode; 7e05a25 P-76 wn link; merged 520b16d"),
        "F2": ("files", "31fff27 P-77 Gemini CLI and Cursor adapters; merged 189d21e"),
        "F3": ("files", "8c42b82 P-78 doctor one line per agent; merged a0a54b9"),
        "F4": ("files", "d680621 P-82 added; 3c1bd76 built; merged 0d07568"),
        "F5": ("files", "live results in progress/P-75.md, P-77.md, P-78.md"),
        "D1": ("decisions", "ship without a Cursor live check (user, 2026-11-16)"),
        "D2": ("decisions", "Cursor has no prompt hook mapped; wrap up uses `wn wrap-up-instructions`"),
        "D3": ("decisions", "Gemini and Cursor hooks are optional in doctor"),
        "C1": ("constraints", "standard library only, Python 3.9+"),
        "C2": ("constraints", "do not push or create a remote without asking"),
        "C3": ("constraints", "run the unittest suite before reporting done (7 to 12 minutes)"),
        "C4": ("constraints", "use plan commands, not hand edits to PLAN.md"),
        "C5": ("constraints", "tests use a temp HOME, never the real agent folders"),
        "Q1": ("open", "Gemini CLI steps 1 to 5 not run: sign-in refused"),
        "Q2": ("open", "Cursor live check not done; session_id vs conversation_id unknown"),
        "Q3": ("open", "Gemini transcript format undocumented; handoff sections may be thin"),
        "X1": ("deadend", "Gemini CLI with Google sign-in: no longer supported"),
        "X2": ("deadend", "Antigravity as a Gemini adapter test: reads other files; used as AGENTS.md-only test"),
    },
}

# ---------------------------------------------------------------------------------------------------------------
# Hand-recorded judgment, part 2: per summary, which handoff facts it restates (overlap) and which it contradicts
# (conflict). The regex must match the summary block. Conflict kinds:
#   stale  = the note is older than the work (or about another task) and now says something else
#   contra = both current, same slot, different value (none found)
# ---------------------------------------------------------------------------------------------------------------
# Constraint lines every early test summary carries (they come from AGENTS.md, which the note repeats).
EARLY_OVERLAP = {
    "C1": r"standard[- ]library only",
    "C2": r"do not push",
    "C4": r"unittest discover|run the tests before",
}
EARLY_CONFLICT = {
    "G1": (r"P-39", "stale", "note: ship the release, all 31 items built; summary: P-39 tips-band check is the task"),
    "N1": (r"Next tip", "stale", "note: try three unverified hooks, run doctor; summary: P-39 manual band check"),
}
H3_OVERLAP = {
    "C1": r"standard[- ]library only",
    "C2": r"do not push|no push",
    "C4": r"unittest discover|run the tests before",
    "Q1": r"tsconfig\.json",
}
H3_CONFLICT = {
    "N1": (r"Next tip", "stale", "note: check the resume note shows 'Before the compact the user asked'; "
                                  "summary (from progress file): check the tips band"),
}
# H3 fact S2 ("not seen in a real session yet") is contradicted by ba2f15bf and c5137415, but only inside their
# <analysis> block ("the compact output listed 'hi'"); the <summary> block does not carry it, so it is not a conflict.

def without(d, *keys):
    return {k: v for k, v in d.items() if k not in keys}


JUDGE = {
    "55d1fcd8": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "2b841192": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "02cc7693": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "d8fb79c6": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "f7c22e49": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "6ffd59c4": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP, C3=r"under 30 lines"), "conflict": dict(EARLY_CONFLICT)},
    "76d432c7": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "b0b57b52": {"handoff": "H1", "overlap": dict(EARLY_OVERLAP), "conflict": dict(EARLY_CONFLICT)},
    "ba2f15bf": {"handoff": "H3", "overlap": without(H3_OVERLAP, "C2"), "conflict": dict(H3_CONFLICT)},
    "e6fc9110": {"handoff": "H3", "overlap": without(dict(H3_OVERLAP, D1=r"ADR-0015 \(accepted\)",
                                                           G1=r"repeat the latest request and open work"), "C2"),
                 "conflict": dict(H3_CONFLICT)},
    "1d1c8054": {"handoff": "H3", "overlap": dict(H3_OVERLAP), "conflict": dict(H3_CONFLICT)},
    "6090a150": {"handoff": "H3", "overlap": without(H3_OVERLAP, "C1", "C2"), "conflict": dict(H3_CONFLICT)},
    "0e994395": {"handoff": "H3", "overlap": without(H3_OVERLAP, "C2"), "conflict": dict(H3_CONFLICT)},
    "c5137415": {"handoff": "H3", "overlap": without(H3_OVERLAP, "C2"), "conflict": dict(H3_CONFLICT)},
    "661478a5": {  # idle wrap-up test; its own note (.whatsnext/sessions/idle3-HANDOFF.md) no longer exists
        "handoff": "H3",
        "overlap": {"C1": r"standard[- ]library only", "C2": r"do not push", "C4": r"unittest discover"},
        "conflict": {"G1": (r"Idle wrap-up test session|wrap up.*idle|idle wrap-up", "stale",
                            "note: carry the latest request after a compact; summary: idle wrap-up test"),
                     "N1": (r"Send the three closing lines", "stale",
                            "note: finish P-39 band/carry check; summary: send the wrap-up closing lines")},
    },
    "a09a001d": {
        "handoff": "H_a09",
        "overlap": {
            "G1": r"new skills/whatsnext/scripts/wn/prbody\.py",
            "N1": r"Commit P-61, mark it done",
            "N2": r"plan done P-61 --verify",
            "N3": r"git merge --ff-only",
            "S1": r"P-61 files are uncommitted",
            "S2": r"15e90e1",
            "S3": r"Nothing is pushed",
            "T1": r"660 tests in 407",
            "F1": r"cmd_pr_body",
            "F2": r"tests/test_prbody\.py",
            "F3": r"P-57: wn/wrapup\.py",
            "F4": r"dfbf33f",
            "F5": r"drop tsconfig",
            "D1": r"ADR-0022:",
            "D2": r"ADR-0023:",
            "D3": r"ADR-0021 was missing",
            "C1": r"do not push",
            "C2": r"standard[- ]library",
            "C3": r"only on the user's approval",
            "C4": r"merge each finished branch into main",
            "C5": r"P-52\.md",
            "Q1": r"Unanswered question to the user",
            "X1": r"Matching saved runs on the commit",
            "X2": r"git branch --merged",
        },
        "conflict": {},
    },
    "c917f1f8": {
        "handoff": "H_c917",
        "overlap": {
            "G1": r"Make whatsnext work in any coding agent",
            "N1": r"Run `wn status`",
            "N2": r"wn plan list",
            "N3": r"run `wn plan check`",
            "S1": r"Done and merged into main",
            "S2": r"Marked done\* with evidence",
            "S3": r"Nothing is pushed",
            "T1": r"448 s",
            "F1": r"584d5e4",
            "F2": r"31fff27",
            "F3": r"8c42b82",
            "F4": r"d680621",
            "F5": r"Progress logs with live results",
            "D1": r"Ship without a Cursor live check",
            "D2": r"Cursor has no prompt hook mapped",
            "D3": r"optional: not being installed",
            "C1": r"Standard library only",
            "C2": r"do not push",
            "C3": r"Run `python3 -m unittest discover",
            "C4": r"Change PLAN\.md through plan commands",
            "C5": r"Tests use a temp HOME",
            "Q1": r"Gemini CLI steps 1 to 5 were not run",
            "Q2": r"Cursor: no live check yet",
            "Q3": r"transcript format is undocumented",
            "X1": r"Gemini CLI with Google sign-in failed",
            "X2": r"Antigravity as a test of the Gemini adapter",
        },
        "conflict": {},
    },
}


# ---------------------------------------------------------------------------------------------------------------
# Mechanical parts
# ---------------------------------------------------------------------------------------------------------------
def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True, check=True).stdout


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def header(text, key):
    m = re.search(r"^%s:\s*(.+)$" % key, text, re.M)
    return m.group(1).strip() if m else None


def written_key(stamp):
    """'2026-11-06T22:56Z' -> sortable 'YYYYMMDDTHHMM'; None when unparsable."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)", stamp or "")
    return "".join(m.groups()[:3]) + "T" + "".join(m.groups()[3:]) if m else None


def handoff_versions():
    """Every distinct note text: git history of HANDOFF.md, the current file, the archive folder."""
    seen = {}
    log = git("log", "--format=%H %aI", "--follow", "--", HANDOFF).split("\n")
    for line in reversed([l for l in log if l.strip()]):  # oldest first
        sha, when = line.split()
        text = git("show", "%s:%s" % (sha, HANDOFF))
        digest = hashlib.sha1(text.encode()).hexdigest()
        seen[digest] = {"label": "HANDOFF.md@%s" % sha[:7], "text": text, "commit_time": when}
    for path in sorted(glob.glob(os.path.join(ARCHIVE, "*.md"))):
        text = read(path)
        digest = hashlib.sha1(text.encode()).hexdigest()
        name = "archive/" + os.path.basename(path)
        if digest in seen:
            seen[digest]["label"] += " = " + name
        else:
            seen[digest] = {"label": name, "text": text, "commit_time": ""}
    cur = os.path.join(ROOT, HANDOFF)
    if os.path.isfile(cur):
        text = read(cur)
        digest = hashlib.sha1(text.encode()).hexdigest()
        if digest in seen:
            seen[digest]["label"] += " = working copy"
        else:
            seen[digest] = {"label": "HANDOFF.md (working copy)", "text": text, "commit_time": ""}
    out = []
    for v in seen.values():
        v["written"] = written_key(header(v["text"], "Written"))
        v["session"] = header(v["text"], "Session")
        v["task"] = header(v["text"], "Task")
        out.append(v)
    return sorted(out, key=lambda v: (v["written"] or "", v["commit_time"]))


def load_summaries():
    rows = []
    for md in sorted(glob.glob(os.path.join(SESSIONS, "*.summary.md"))):
        sid = os.path.basename(md)[:-len(".summary.md")]
        meta = json.loads(read(md[:-3] + ".json"))
        sess = {}
        for suffix in (".json",):
            p = os.path.join(SESSIONS, sid + suffix)
            if os.path.isfile(p):
                sess = json.loads(read(p))
        compact = {}
        p = os.path.join(SESSIONS, sid + ".compact.json")
        if os.path.isfile(p):
            compact = json.loads(read(p))
        text = read(md)
        m = re.search(r"<summary>(.*)</summary>", text, re.S)
        a = re.search(r"<analysis>(.*?)</analysis>", text, re.S)
        rows.append({
            "id": sid, "short": sid[:8], "saved": written_key(meta.get("saved")), "saved_text": meta.get("saved"),
            "item": sess.get("item"), "branch": sess.get("branch"), "text": text,
            "summary": m.group(1) if m else text, "analysis": a.group(1) if a else "",
            "carry": compact.get("carry"),
        })
    return sorted(rows, key=lambda r: r["saved"])


def minutes_between(a, b):
    """Minutes from stamp a to stamp b (both YYYYMMDDTHHMM)."""
    import datetime
    f = "%Y%m%dT%H%M"
    return int((datetime.datetime.strptime(b, f) - datetime.datetime.strptime(a, f)).total_seconds() // 60)


def pair(summary, versions):
    """The latest note written at or before the compact; a note of the same session wins over a later foreign one
    only when it is also at or before the compact. Returns (version, reason)."""
    before = [v for v in versions if v["written"] and v["written"] <= summary["saved"]]
    if not before:
        return None, "no note written before the compact"
    same = [v for v in before if v["session"] == summary["id"]]
    if same:
        return same[-1], "same session wrote it"
    return before[-1], "latest note before the compact (written by another session)"


HEADING = re.compile(r"^(\d+\.\s+)?\**[A-Z][A-Za-z ,&/()'-]{2,60}:\**$")
LEAD = re.compile(r"^\d+\.\s+\**[A-Z][A-Za-z ,&/()'-]{2,50}:\**\s+(?=\S)")


def units_of(block):
    """(units, heading_bytes): sentence-level units of a summary block, and the bytes of pure heading lines."""
    units, heads = [], 0
    for raw in block.split("\n"):
        line = re.sub(r"^\s*(?:[-*]\s+)", "", raw).strip()
        if not line:
            continue
        if HEADING.match(line):
            heads += len(raw.encode()) + 1
            continue
        line = LEAD.sub("", line)
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z(`\"*])", line):
            part = part.strip()
            if len(part) >= 3:
                units.append(part)
    return units, heads


def words(text):
    return re.findall(r"[a-z0-9_./+-]+", text.lower())


def shingles(text, n=4):
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def lexical_share(summary_block, note_text):
    """Share of the summary's word 4-grams that also occur in the note (independent of the hand judgment)."""
    s = shingles(summary_block)
    return len(s & shingles(note_text)) / len(s) if s else 0.0


# Hand judgment, part 3: for the two same-session pairs, the top-level sections of the summary that mostly restate
# the note (a coarser estimate of the overlap, shown next to the unit-level count; it can be higher or lower).
OVERLAP_SECTIONS = {
    "c917f1f8": {"Goal", "Next action", "State", "Decisions", "Instructions", "Open questions", "Dead ends"},
    "a09a001d": {"Problem Solving", "Pending Tasks", "Current Work", "Optional Next Step"},
}

MISSING = []


def section_profile(block):
    """[(title, bytes)] for the top-level sections of a summary block (unindented heading lines)."""
    out, title, size = [], "(before first heading)", 0
    for raw in block.split("\n"):
        if raw and not raw[0].isspace() and HEADING.match(raw.strip()):
            out.append((title, size))
            title, size = re.sub(r"^\d+\.\s+|:\**$|^\**", "", raw.strip()), 0
            title = re.sub(r"\**$", "", title)
            continue
        size += len(raw.encode()) + 1
    out.append((title, size))
    return [(a, b) for a, b in out if b > 0]


def judge(summary, version):
    j = JUDGE[summary["short"]]
    facts = FACTS[j["handoff"]]
    block = summary["summary"]
    units, heads = units_of(block)
    flags = [set() for _ in units]  # per unit: {("O", fid)} / {("C", fid)}
    lower = 0
    for fid, rx in j["overlap"].items():
        hits = [i for i, u in enumerate(units) if re.search(rx, u, re.I)]
        if not hits:
            MISSING.append("%s overlap %s: /%s/" % (summary["short"], fid, rx))
            continue
        for i in hits:
            flags[i].add(("O", fid))
        m = re.search(rx, units[hits[0]], re.I)
        lower += len(m.group(0).encode())
    for fid, (rx, kind, _note) in j["conflict"].items():
        hits = [i for i, u in enumerate(units) if re.search(rx, u, re.I)]
        if not hits:
            MISSING.append("%s conflict %s: /%s/" % (summary["short"], fid, rx))
            continue
        flags[hits[0]].add(("C", fid))  # the unit that states the diverging value
    o_ids = set(j["overlap"])
    c_ids = set(j["conflict"])
    assert not (o_ids & c_ids), "a fact cannot be both overlap and conflict"
    o_units = [i for i, f in enumerate(flags) if any(k == "O" for k, _ in f)]
    o_units_nc = [i for i in o_units if any(k == "O" and facts[fid][0] != "constraints" for k, fid in flags[i])]
    c_only = [i for i, f in enumerate(flags) if f and i not in o_units]
    bytes_of = lambda idx: sum(len(units[i].encode()) + 1 for i in idx)
    cats = {}
    for fid, (cat, _t) in facts.items():
        cats.setdefault(cat, {"n": 0, "o": 0, "c": 0})
        cats[cat]["n"] += 1
        cats[cat]["o"] += fid in o_ids
        cats[cat]["c"] += fid in c_ids
    n = len(facts)
    return {
        "handoff": j["handoff"], "H": n, "O": len(o_ids), "C": len(c_ids), "Ho": n - len(o_ids) - len(c_ids),
        "O_nc": len([f for f in o_ids if facts[f][0] != "constraints"]),
        "units": len(units), "o_units": len(o_units), "c_units": len(c_only),
        "So": len(units) - len(o_units) - len(c_only),
        "summary_bytes": len(block.encode()), "file_bytes": len(summary["text"].encode()),
        "analysis_bytes": len(summary["analysis"].encode()), "heading_bytes": heads,
        "ov_bytes": bytes_of(o_units), "ov_bytes_low": lower, "ov_bytes_nc": bytes_of(o_units_nc),
        "cats": cats,
        "conflicts": [(fid, kind, note) for fid, (_rx, kind, note) in j["conflict"].items()],
        "lexical": lexical_share(block, version["text"]),
    }


def pct(a, b):
    return "%.0f%%" % (100.0 * a / b) if b else "n/a"


def main():
    versions = handoff_versions()
    summaries = load_summaries()
    out = []
    p = out.append

    p("## Pairing (mechanical)")
    p("")
    p("%d saved summaries; %d distinct handoff versions found." % (len(summaries), len(versions)))
    p("")
    p("| summary | compact (UTC) | item | note paired | note written (UTC) | age (min) | same session | rule |")
    p("|---|---|---|---|---|---|---|---|")
    pairs = []
    for s in summaries:
        v, why = pair(s, versions)
        if v is None:
            p("| %s | %s | %s | UNPAIRED | | | | %s |" % (s["short"], s["saved_text"], s["item"] or "-", why))
            continue
        age = minutes_between(v["written"], s["saved"])
        same = "yes" if v["session"] == s["id"] else "no"
        p("| %s | %s | %s | %s | %s | %d | %s | %s |" % (
            s["short"], s["saved_text"], s["item"] or "-", v["label"], v["written"][:4] + "-" + v["written"][4:6] + "-" +
            v["written"][6:8] + " " + v["written"][9:11] + ":" + v["written"][11:] + "Z", age, same, why))
        pairs.append((s, v))
    p("")

    results = []
    for s, v in pairs:
        r = judge(s, v)
        results.append((s, v, r))

    p("## Facts per pair (hand judgment, regex-anchored)")
    p("")
    p("H = facts in the note; O = in both; C = conflict; Ho = only in the note (O+C+Ho = H). "
      "units = sentence units in the summary block; ov = units that restate note facts; So = summary-only units.")
    p("")
    p("| summary | note | H | O | C | Ho | units | ov units | So | summary bytes | ov bytes (units) | ov bytes (matched text) | ov % | ov % without constraints | lexical 4-gram % |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    tot = {k: 0 for k in ("H", "O", "C", "Ho", "units", "o_units", "So", "summary_bytes", "file_bytes", "ov_bytes",
                          "ov_bytes_low", "ov_bytes_nc", "O_nc", "c_units")}
    for s, v, r in results:
        p("| %s | %s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %s | %s | %.0f%% |" % (
            s["short"], r["handoff"], r["H"], r["O"], r["C"], r["Ho"], r["units"], r["o_units"], r["So"],
            r["summary_bytes"], r["ov_bytes"], r["ov_bytes_low"], pct(r["ov_bytes"], r["summary_bytes"]),
            pct(r["ov_bytes_nc"], r["summary_bytes"]), 100 * r["lexical"]))
        for k in tot:
            tot[k] += r[k]
    p("")

    def block(title, subset):
        t = {k: sum(r[k] for _s, _v, r in subset) for k in tot}
        p("- %s (%d pairs): H=%d, O=%d, C=%d, Ho=%d; summary units=%d, overlap units=%d, summary-only units=%d; "
          "summary bytes=%d, overlap bytes=%d (%s; matched text only %s; without constraint lines %s)" % (
              title, len(subset), t["H"], t["O"], t["C"], t["Ho"], t["units"], t["o_units"], t["So"],
              t["summary_bytes"], t["ov_bytes"], pct(t["ov_bytes"], t["summary_bytes"]),
              pct(t["ov_bytes_low"], t["summary_bytes"]), pct(t["ov_bytes_nc"], t["summary_bytes"])))

    own = [x for x in results if x[1]["session"] == x[0]["id"]]
    foreign = [x for x in results if x[1]["session"] != x[0]["id"]]
    p("## Totals")
    p("")
    block("all", results)
    block("own fresh note (same session)", own)
    block("another session's note", foreign)
    p("")
    p("Bytes: summary block = text inside <summary>; the saved files also hold an <analysis> block "
      "(total file bytes %d, summary-block bytes %d)." % (tot["file_bytes"], tot["summary_bytes"]))
    p("")

    p("## Conflicts (hand judgment)")
    p("")
    for s, v, r in results:
        for fid, kind, note in r["conflicts"]:
            p("- %s [%s %s]: %s" % (s["short"], r["handoff"], fid, note))
    p("")
    p("Conflict kinds: all %d are 'stale' (the note is older than the work or about other work); 0 are 'contra' "
      "(both current, same slot, different value)." % tot["C"])
    p("")

    p("## Sections of the two same-session summaries (bytes)")
    p("")
    for s, v, r in own:
        prof = section_profile(s["summary"])
        mark = OVERLAP_SECTIONS[s["short"]]
        hit = sum(b for a, b in prof if any(a.lower().startswith(m.lower()) for m in mark))
        p("- %s: %s" % (s["short"], "; ".join("%s %d%s" % (a, b, "*" if any(a.lower().startswith(m.lower()) for m in mark) else "")
                                              for a, b in prof)))
        p("  sections marked * mostly restate the note: %d of %d bytes (%s), a section-level estimate" % (
            hit, r["summary_bytes"], pct(hit, r["summary_bytes"])))
    p("")
    p("## Facts by category (all pairs / same-session pairs)")
    p("")
    p("| category | facts x pairs | in both | conflict | in both, same-session | facts x pairs, same-session |")
    p("|---|---|---|---|---|---|")
    order = ["goal", "next", "state", "tests", "files", "decisions", "constraints", "open", "deadend"]
    for cat in order:
        a = [sum(r["cats"].get(cat, {}).get(k, 0) for _s, _v, r in results) for k in ("n", "o", "c")]
        b = [sum(r["cats"].get(cat, {}).get(k, 0) for _s, _v, r in own) for k in ("n", "o")]
        p("| %s | %d | %d | %d | %d | %d |" % (cat, a[0], a[1], a[2], b[1], b[0]))
    p("")

    if MISSING:
        raise SystemExit("judgment drift: these hand-recorded anchors match no unit in the summary text:\n  " +
                         "\n  ".join(MISSING))
    print("\n".join(out))
    unpaired = [s["short"] for s in summaries if pair(s, versions)[0] is None]
    if unpaired:
        print("UNPAIRED: %s" % ", ".join(unpaired))
    return 0


if __name__ == "__main__":
    sys.exit(main())
