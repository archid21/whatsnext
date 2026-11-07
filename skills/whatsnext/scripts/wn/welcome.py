"""The first-run welcome (P-44): a table of what whatsnext does, shown once after install.

`whatsnext welcome` prints it. The SessionStart hook shows it the first time a session starts after install and
writes a marker beside the user settings, so it does not show twice. `/whatsnext-welcome` (Claude Code) shows it again.
"""

import os
import textwrap

from . import config as gwconfig

MARKER_NAME = "welcomed"
WIDTHS = (18, 38, 42)
HEAD = ("Feature", "What it does", "How it works")

# The first five rows are the ones to understand and use first; the rest are extras.
ROWS = (
    ("Set up your plan",
     'Say "set up whatsnext in this repo", then "add these items to the plan". "what\'s next?" shows what to do next.',
     "`init` makes PLAN.md, a checklist in your repo. `plan add`, `plan drop` and `plan move` edit it. `plan next` picks the first open item."),
    ("Start work",
     'Say "start P-13". The agent asks a few questions, then you choose: run all steps, or one step at a time.',
     "`plan start` leaves a note that you hold the item, and refuses one another agent holds. A note, not a lock."),
    ("Change the plan",
     'Say "add an item: ...", "drop P-16", "move P-14 to Later", or "import the plan from <file or folder>" (any tool\'s spec or task list).',
     "The agent uses the plan commands, so ids are never reused. An import is the agent reading your file, never a fixed parser."),
    ("Mark done with proof",
     'Say "mark P-13 done". The item is ticked only if your test command passes. No more "trust me, it works".',
     "`plan done --verify` runs the command. Exit 0 ticks it; otherwise it stays open and shows the last 20 lines of output."),
    ("Save and resume",
     'Say "wrap up" to save your goal, next step and decisions. The next session starts from them.',
     "A hook writes docs/project/HANDOFF.md. A resume note of at most 1,200 characters loads at session start, after /clear and after a compact."),
    ("Smart compact",
     "When Claude shortens a long chat, it keeps your goal instead of guessing what mattered.",
     "`compact-instructions` builds the /compact text from your handoff."),
    ("Auto wrap-up",
     "Opt-in. If you step away for 45 minutes, your handoff is saved before Claude's own idle compact.",
     "A timer in the Claude Code module. Off by default: the setting `wrapup.autoIdle`, offered by a tip. Runs once per idle period."),
    ("Task progress files",
     "A notebook per task: goal, what is done, the exact next step.",
     "`docs/project/progress/P-NN.md`, with a journal of time, commit and files changed. No model call."),
    ("Tips",
     "A small hint bar that teaches the phrases above, one at a time, when they apply.",
     "Claude Code only. Next tip and Stop tips buttons; `/whatsnext-tips` brings it back."),
    ("Claude Code and Codex",
     "Both agents share the same plan and notes. Switching between them is experimental.",
     "Plain Markdown and JSON files, read and written by the same `whatsnext.py` commands."),
)

FLOW = '''How it fits together:

   YOU WORK
      |  a long session, or you step away
      v
   SAVE ------------------------------------------------------.
    "wrap up", or auto wrap-up at 45 idle minutes (opt-in)     |
      |                                                        |
      v                                                        |
   HANDOFF.md written: goal, next step, decisions              |
      |                                                        |
      v                                                        |
   CLEAR OR COMPACT                                            |
    auto-compact (if on), /compact or /clear                   |
      |                                                        |
      v                                                        |
   RESUME: a short note loads, with what is done and what is next
      |                                                        |
      v                                                        |
   "what's next?" > "start P-13" > work > "mark P-13 done" ----'
    (a plan item, and a test command that must pass)

Auto-compact off: nothing saves a handoff for you. Say "wrap up" before you /clear or /compact.'''


def _row(cells):
    wrapped = [textwrap.wrap(c, w) or [""] for c, w in zip(cells, WIDTHS)]
    height = max(len(w) for w in wrapped)
    lines = []
    for i in range(height):
        parts = [(w[i] if i < len(w) else "").ljust(width) for w, width in zip(wrapped, WIDTHS)]
        lines.append((" | ".join(parts)).rstrip())
    return lines


def render():
    """The whole welcome as plain text."""
    rule = "-+-".join("-" * w for w in WIDTHS)
    out = ["whatsnext: one plan, one next step, for every coding agent", "",
           "A plan checklist, check-offs and a resume note, kept as plain files in your repo.", ""]
    out += _row(HEAD) + [rule]
    for n, row in enumerate(ROWS):
        out += _row(row)
        if n == 4:
            out.append(rule)  # the five to learn first end here
    out += ["", FLOW, "", "Start here: say `what's next?`, or `set up whatsnext in this repo`.",
            "See this again any time: /whatsnext-welcome (Claude Code) or `whatsnext welcome`.",
            "Guide: https://github.com/archid21/whatsnext/blob/main/docs/GUIDE.md"]
    return "\n".join(out) + "\n"


def marker_path():
    return os.path.join(os.path.dirname(gwconfig.user_config_path()), MARKER_NAME)


def take_first_run(data):
    """The welcome text the first time a session starts after install, else "". It writes the marker, so it is
    said once. Only a fresh start counts (not a resume, /clear or compact)."""
    if data.get("source") not in (None, "startup"):
        return ""
    path = marker_path()
    if os.path.exists(path):
        return ""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("shown\n")
    except OSError:  # no marker could be written: say nothing, rather than say it every session
        return ""
    return render()


def run(args):
    print(render(), end="")
    return 0
