"""`fresh-instructions` (ADR-0025): what another plugin needs to wrap up and start fresh, seeded with the handoff.

Read-only. The handoff values come from the same code as `compact-instructions --json`. The start-fresh texts here
are the one source; `hooks/newchat.ts` keeps a copy for whatsnext's band (ADR-0024) and a test keeps them equal.
"""

import argparse
import json
import sys

from . import compact as gwcompact
from . import config as gwconfig
from . import hook as gwhook
from . import sessions as gwsessions
from . import wrapup as gwwrapup

# The new chat's first prompt. The session-start hook already puts the resume note (with the handoff) in context.
CONTINUE = "Continue from the handoff note: read it first."

# The desktop app: the agent starts the session with the app's own session tool, as no mod call can.
NEW_SESSION_PROMPT = (
    'Start a new session for this project with the start_session tool (initiation "user_asked", context "fresh"), '
    'titled "Continue from the handoff". Its first prompt, word for word: "%s" '
    "Then stop: do nothing else in this session." % CONTINUE
)

# The terminal: no portable way to open a window, so the person runs this in a new one.
TERMINAL_COMMAND = 'claude "%s"' % CONTINUE

# Run before CONTINUE for Clear and continue (the old chat stays in /resume).
CLEAR_COMMAND = "clear"


def steps(root, effective, session_id, transcript):
    """The JSON a caller reads: handoff state (as compact-instructions gives it), then the start-fresh texts."""
    handoff = gwwrapup.handoff_path(root, effective)
    state = gwwrapup.handoff_state(handoff, transcript, session_id, root)
    return {
        "project": gwhook.is_project(root, effective),
        "session_found": transcript is not None,
        "handoff": gwconfig.display_path(handoff, root),
        "handoff_exists": state["exists"],
        "handoff_foreign": state["foreign"],
        "wrap_up_first": state["stale"],
        "wrap_up_state": gwcompact.wrap_up_state(root, session_id, state),
        "wrap_up_prompt": gwwrapup.PROMPT,
        "continue_prompt": CONTINUE,
        "new_session_prompt": NEW_SESSION_PROMPT,
        "terminal_command": TERMINAL_COMMAND,
        "clear_command": CLEAR_COMMAND,
    }


def cmd_instructions(argv):
    parser = argparse.ArgumentParser(prog="whatsnext fresh-instructions",
                                     description="Print what a caller needs to wrap up and start a fresh chat from the handoff.")
    parser.add_argument("--session", help="the session id; lets the handoff be checked against the session's last turn")
    parser.add_argument("--project", help="the project folder (default: the session's start folder, else this folder)")
    parser.add_argument("--json", action="store_true", help="print the steps for a caller as JSON")
    args = parser.parse_args(argv)
    if args.session is not None and not gwsessions.valid_session_id(args.session):
        print("not a session id: %r" % args.session, file=sys.stderr)
        return 1
    transcript = gwsessions.find_transcript(args.session) if args.session else None
    root, effective = gwcompact.project_for(args, transcript)
    data = steps(root, effective, args.session, transcript)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    if data["wrap_up_first"]:
        print("Wrap up first: submit `%s`." % data["wrap_up_prompt"])
    print("New chat's first prompt: " + CONTINUE)
    print("In a new terminal window: " + TERMINAL_COMMAND)
    return 0
