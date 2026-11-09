"""Start while another session is live in this checkout (ADR-0020).

`plan start` asks where the new item should go (a new worktree or this branch). The answers are counted per
project in `.whatsnext/sessions/concurrent-start.json` (git-ignored, like the other session state, and removed by the
same SessionStart prune after 14 idle days, ADR-0018): `{"last": "worktree", "streak": 1}`. After two equal
`worktree` answers in a row, Start offers to save `plan.concurrentStart = worktree`. After an offer the count starts
again, so ignoring the offer means "keep asking". `stay` is never offered as an "always".
"""

import json
import os

from . import journal as gwjournal
from . import util

STATE_FILE = "concurrent-start.json"
ANSWERS = ("worktree", "stay")
OFFER_AFTER = 2  # equal worktree answers in a row
OFFER_TEXT = "Always use a new worktree when another session is working here?"


def state_path(root):
    return os.path.join(root, gwjournal.SESSIONS_DIR, STATE_FILE)


def read_state(root):
    """{"last": answer or None, "streak": int}. Anything unreadable reads as no answers yet."""
    path = state_path(root)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"last": None, "streak": 0}
    last = data.get("last") if isinstance(data, dict) else None
    streak = data.get("streak") if isinstance(data, dict) else None
    if last not in ANSWERS or not isinstance(streak, int) or isinstance(streak, bool) or streak < 0:
        return {"last": None, "streak": 0}
    return {"last": last, "streak": min(streak, 1000)}


def record_answer(root, answer):
    """Count one user answer (`worktree` or `stay`). Returns True when the "always worktree" offer is due.
    A state file that cannot be written means no offer (it must never stop Start)."""
    if answer not in ANSWERS:
        return False
    state = read_state(root)
    streak = state["streak"] + 1 if state["last"] == answer else 1
    offer = answer == "worktree" and streak >= OFFER_AFTER
    state = {"last": answer, "streak": 0 if offer else streak}
    path = state_path(root)
    if os.path.islink(path) or os.path.islink(os.path.dirname(path)) or os.path.islink(os.path.dirname(os.path.dirname(path))):
        return False  # never write through a link
    try:
        util.write_atomic(path, json.dumps(state) + "\n", newline=None)
    except OSError:
        return False
    return offer


def offer_info(item_id):
    """The machine-readable offer, and its one line of text."""
    command = "plan start %s --concurrent worktree --always" % item_id
    return {"setting": "plan.concurrentStart", "value": "worktree", "text": OFFER_TEXT, "answer": command,
            "line": "Offer: %s To say yes, run: %s" % (OFFER_TEXT, command)}
