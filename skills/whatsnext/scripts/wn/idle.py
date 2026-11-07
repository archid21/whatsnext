"""The idle wrap-up check (ADR-0016, P-40).

Claude Code's hooks module (hooks/register.tsx) waits 45 minutes after the last main-thread turn, then asks
this check whether to submit `wrap up`. The module knows the things only it can read (the context size, Claude
Code's own settings); this check knows the whatsnext side:

- `wrapup.autoIdle` is on (default off),
- the folder is a whatsnext project (the caller's gate),
- this session has no fresh wrap-up (ADR-0008).

It prints one JSON line, `{"fire": true}` or `{"fire": false, "reason": "..."}`. When it says fire, it also
writes the time to the git-ignored `.whatsnext/sessions/<session>.idle.json` (`asked`), so a test run can read
when `wrap up` was submitted. Any error reads as "do not fire".
"""

import json
import os

from . import journal as gwjournal
from . import sessions as gwsessions
from . import wrapup as gwwrapup
from .util import now_utc, write_atomic

IDLE_MINUTES = 45  # the module's timer; Claude Code's idle compact came 54 minutes after the last request (ADR-0016)


def idle_path(root, session_id):
    name = gwjournal.safe_session_id(session_id)
    return os.path.join(root, gwjournal.SESSIONS_DIR, name + ".idle.json") if name else None


def decide(root, effective, data):
    """(fire, reason): reason is "" when fire is true."""
    if not effective.get("wrapup.autoIdle"):
        return False, "wrapup.autoIdle is off"
    session_id = data.get("session_id")
    if not gwsessions.valid_session_id(session_id):
        return False, "no session id"
    transcript = data.get("transcript_path")
    if not (isinstance(transcript, str) and os.path.isfile(transcript)):
        transcript = gwsessions.find_transcript(session_id)
    state = gwwrapup.handoff_state(gwwrapup.handoff_path(root, effective), transcript, session_id, root)
    if state["exists"] and not state["stale"]:
        return False, "this session already has a fresh wrap-up"
    return True, ""


def check_text(root, effective, data):
    """The one JSON line the module reads; `fire: true` also records when `wrap up` was asked for."""
    fire, reason = decide(root, effective, data)
    if not fire:
        return json.dumps({"fire": False, "reason": reason})
    path = idle_path(root, data.get("session_id"))
    if path:
        write_atomic(path, json.dumps({"asked": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
    return json.dumps({"fire": True})
