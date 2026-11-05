"""`compact-instructions` (ADR-0009): whatsnext's text for `/compact` in an OPEN session. The caller submits it.

It builds the text from the handoff note, and leaves out a note this session did not write (ADR-0008).
"""

import argparse
import json
import os
import sys

from . import config as gwconfig
from . import hook as gwhook
from . import sessions as gwsessions
from . import wrapup as gwwrapup


def project_for(args, transcript):
    """(root, effective): --project, else the session's start folder, else the current folder."""
    folder = args.project
    if not folder and transcript:
        cwd = gwsessions.transcript_cwd(transcript)
        folder = cwd if cwd and os.path.isdir(cwd) else None
    root = gwconfig.find_root(folder)
    return root, gwconfig.load(root)


def cmd_instructions(argv):
    parser = argparse.ArgumentParser(prog="whatsnext compact-instructions",
                                     description="Print the text that follows `/compact ` in an open session.")
    parser.add_argument("--session", help="the session id; lets the handoff be checked against the session's last turn")
    parser.add_argument("--project", help="the project folder (default: the session's start folder, else this folder)")
    parser.add_argument("--json", action="store_true", help="print the steps for a caller as JSON")
    args = parser.parse_args(argv)
    if args.session is not None and not gwsessions.valid_session_id(args.session):
        print("not a session id: %r" % args.session, file=sys.stderr)
        return 1
    transcript = gwsessions.find_transcript(args.session) if args.session else None
    root, effective = project_for(args, transcript)
    text = gwwrapup.compact_instructions(root, effective, args.session)
    if not args.json:
        print(text)
        return 0
    handoff = gwwrapup.handoff_path(root, effective)
    state = gwwrapup.handoff_state(handoff, transcript, args.session, root)
    line = None
    if state["exists"] and not state["foreign"]:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            line = gwwrapup.compact_line(f.read())
    print(json.dumps({
        "instructions": text,
        "compact_prompt": "/compact " + text,
        "compact_line": line,
        "handoff": gwconfig.display_path(handoff, root),
        "handoff_exists": state["exists"],
        "handoff_foreign": state["foreign"],
        "wrap_up_first": state["stale"],
        "wrap_up_state": wrap_up_state(root, args.session, state),
        "wrap_up_prompt": gwwrapup.PROMPT,
        "project": gwhook.is_project(root, effective),
        "session_found": transcript is not None,
    }, indent=2))
    return 0


def wrap_up_state(root, session_id, state):
    """`requested` while the wrap-up marker exists (the prompt came, Stop has not run), `written` when this
    session's note is fresh (its sidecar matches the file and no turn came after it), else `none`."""
    marker = gwwrapup.marker_path(root, session_id) if session_id else None
    if marker and os.path.isfile(marker):
        return "requested"
    if session_id and state["exists"] and not state["stale"]:
        return "written"
    return "none"
