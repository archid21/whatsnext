"""Tracker sync (P-79, ADR-0027 rule 5): read ready items from Beads or GitHub Issues through the user's own
`bd` or `gh`, and close one there after the user says so. whatsnext makes no network call itself; PLAN.md stays
the source of truth for check-offs."""

import json
import re
import shutil
import subprocess

TIMEOUT = 120
SOURCES = ("beads", "github")
TOOL = {"beads": "bd", "github": "gh"}
NAME = {"beads": "Beads", "github": "GitHub"}
TRACKER_RE = re.compile(r"^tracker\s*:\s*(\S+)\s*$", re.I)
GH_RE = re.compile(r"\Agh#(\d+)\Z")
BD_RE = re.compile(r"\Abd:([A-Za-z0-9][A-Za-z0-9._-]*)\Z")


class TrackerError(Exception):
    pass


def tracker_id(source, raw):
    """The id kept in PLAN.md: `gh#12` or `bd:<id>`."""
    return ("gh#%s" % raw) if source == "github" else ("bd:%s" % raw)


def run_tool(root, argv):
    """Run `bd` or `gh` from the project root; its stdout, or TrackerError with the reason."""
    if shutil.which(argv[0]) is None:
        raise TrackerError("`%s` is not installed or not on the PATH. whatsnext uses only your own `%s`."
                           % (argv[0], argv[0]))
    try:
        proc = subprocess.run(argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise TrackerError("`%s` did not finish in %d s." % (" ".join(argv), TIMEOUT))
    except OSError as exc:
        raise TrackerError("`%s` could not run: %s" % (" ".join(argv), exc))
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise TrackerError("`%s` failed (exit %d): %s" % (" ".join(argv), proc.returncode, " ".join(tail)))
    return proc.stdout


def fetch(root, source):
    """Ready items as [{"tracker": id, "title": str, "url": str}], in the tracker's order."""
    if source == "github":
        argv = ["gh", "issue", "list", "--state", "open", "--json", "number,title,url"]
    else:
        argv = ["bd", "ready", "--json"]
    out = run_tool(root, argv)
    try:
        rows = json.loads(out or "[]")
    except ValueError:
        raise TrackerError("`%s` did not print JSON." % " ".join(argv))
    if isinstance(rows, dict):
        rows = rows.get("issues") or rows.get("items") or []
    if not isinstance(rows, list):
        raise TrackerError("`%s` printed JSON that is not a list." % " ".join(argv))
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = row.get("number") if source == "github" else row.get("id")
        title = " ".join(str(row.get("title") or "").split())
        if raw is None or not title:
            continue
        tid = tracker_id(source, raw)
        if not (GH_RE.match(tid) or BD_RE.match(tid)):
            continue
        items.append({"tracker": tid, "title": title, "url": str(row.get("url") or "")})
    return items


def close_argv(tid):
    """The command that closes `tid` in its tracker, or None for an id whatsnext does not know."""
    m = GH_RE.match(tid)
    if m:
        return ["gh", "issue", "close", m.group(1)]
    m = BD_RE.match(tid)
    if m:
        return ["bd", "close", m.group(1)]
    return None


def tracker_name(tid):
    return "GitHub" if tid.startswith("gh#") else "Beads"
