"""`whatsnext status`: one call for "what's next?" and "where did we leave off?" (P-55).

It joins what `plan next`, `plan check` and the resume note already work out: the current item, the handoff note
and how it relates to this session, the ready items and every warning. No model call, nothing is written.
"""

import argparse
import json
import re

from . import claims as gwclaims
from . import packet as gwpacket
from . import plan as gwplan
from . import status as gwstatus

READY_LIMIT = 3
DRIFT_RE = re.compile(r"^(P?[A-Za-z]*-\d+) was .*Run its verify again\.$")


def fold_drift(warnings):
    """`plan check` warns once per done item verified before later commits. For a status that is noise: keep the
    other warnings and put the drifted items on one line, `plan check` lists them in full."""
    drifted = [m.group(1) for m in (DRIFT_RE.match(w) for w in warnings) if m]
    rest = [w for w in warnings if not DRIFT_RE.match(w)]
    if drifted:
        rest.append("%d done item%s verified before later commits (%s). `plan check` lists them; run a verify again "
                    "only when its code changed." % (len(drifted), "" if len(drifted) == 1 else "s",
                                                      ", ".join(drifted[:5]) + (", ..." if len(drifted) > 5 else "")))
    return rest


def build(ctx, session=None, limit=READY_LIMIT):
    """The status as a dict: current, ready, recommended, message, handoff, warnings, errors."""
    session = session or gwstatus.env_session()
    out = {"current": None, "ready": [], "recommended": None, "message": "", "handoff": None,
           "warnings": [], "errors": []}
    if ctx.has_plan():
        views = ctx.views()
        current = gwplan.current_work(ctx, views)
        ready = gwplan.candidates([v for v in views if not current or v["id"] != current["id"]], limit)
        out["current"] = current
        out["ready"] = ready
        out["recommended"] = current["id"] if current else (ready[0]["id"] if ready else None)
        if not current and not ready:
            out["message"] = gwplan.waiting_text(views, ctx.items())
        out["handoff"] = gwplan.handoff_block(ctx, views, out["recommended"])
        out["errors"], warnings = gwplan.check(ctx)
        out["warnings"].extend(fold_drift(warnings))
    else:
        out["message"] = gwplan.no_plan(ctx)
        out["handoff"] = gwplan.handoff_block(ctx)
    task = None
    if out["current"]:
        task = gwstatus.load_tasks(ctx.root, ctx.folder)
        task = next((t for t in task if t.id == out["current"]["id"]), None)
    info = gwpacket.handoff_info(ctx.root, ctx.effective, task, session)
    if info:
        if out["handoff"] is None:  # a note with neither Next action nor open questions
            out["handoff"] = {"path": info["rel"], "written": gwpacket.utc_text(info["written"]), "task": None,
                              "task_status": None, "next_action": "", "open_questions": "", "warnings": []}
        out["handoff"]["read_first"] = info["related"]
        out["handoff"]["label"] = "read it first" if info["related"] else "another session's note"
        out["warnings"].extend(out["handoff"].get("warnings", []))
    for claim, since in gwclaims.stale_in_worktree(ctx.root, ctx.effective):
        out["warnings"].append("%s is stale: idle since %s. Done, keep or put back?" % (
            claim.get("id"), since.strftime("%Y-%m-%dT%H:%MZ") if since else "an unknown time"))
    return out


def print_text(data):
    current = data["current"]
    if current:
        print("Current: %s %s (%s)" % (current["id"], current["title"], current["action"]))
        print("  Next: " + (current.get("step") or current.get("next_action") or "Review the progress file."))
        if current.get("blockers"):
            print("  Blockers: " + current["blockers"])
    if data["ready"]:
        print("Ready:")
        for n, v in enumerate(data["ready"], 1):
            mark = "  [recommended]" if v["id"] == data["recommended"] else ""
            print("  %d. %s %s%s" % (n, v["id"], v["title"], mark))
    if data["message"]:
        print(data["message"])
    handoff = data["handoff"]
    if handoff:
        line = "Handoff: %s, written %s" % (handoff["path"], handoff.get("written") or "at an unknown time")
        if handoff.get("label"):
            line += " (%s)" % handoff["label"]
        print(line)
        if handoff.get("next_action"):
            print("  Next action: " + handoff["next_action"])
        if handoff.get("open_questions"):
            print("  Open questions and blockers: " + handoff["open_questions"])
    else:
        print("Handoff: none.")
    for line in data["errors"]:
        print("Error: " + line)
    for line in data["warnings"]:
        print("Warning: " + line)


def run(argv, cwd=None):
    parser = argparse.ArgumentParser(prog="whatsnext status",
                                     description="current item, handoff, ready items and warnings in one call")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--session", help="this session's id (default: $WHATSNEXT_SESSION)")
    parser.add_argument("--limit", type=int, default=READY_LIMIT, help="ready items to list (default 3)")
    args = parser.parse_args(argv)
    data = build(gwplan.Ctx.load(cwd), args.session, args.limit)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_text(data)
    return 0
