"""`whatsnext doctor` (P-18): are the hooks in place for each agent, and when did one last fire?

It reads files only. It never changes a file and runs no agent. Claude Code: the plugin's `hooks/hooks.json` names
every event whatsnext needs. Codex: `~/.codex/hooks.json` (and the project's `.codex/hooks.json`) hold whatsnext's
entries. Codex trusts hooks in its own `/hooks` screen; whatsnext cannot read that, so it says so.
"""

import glob
import json
import os
import re
import sys

from . import config as gwconfig
from . import hooksinstall as gwhooksinstall
from . import journal as gwjournal
from . import sessions as gwsessions

CLAUDE_COMMAND = re.compile(r"whatsnext\.py[\"']?\s+hook\s+(\S+)\s+--agent\s+claude-code\b")
CLAUDE_EVENTS = ("session-start", "plan-shown", "plan-approved", "prompt-submit", "stop", "pre-compact",
                 "post-compact", "session-end")
PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *([os.pardir] * 4)))  # wn -> scripts -> whatsnext -> skills -> plugin


def claude_hooks(path=None):
    """(events found in the plugin's hooks.json, error)."""
    path = path or os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return set(), "cannot read %s: %s" % (path, e)
    found = set()
    for groups in (data.get("hooks") or {}).values() if isinstance(data, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for handler in (group.get("hooks") or []) if isinstance(group, dict) else []:
                m = CLAUDE_COMMAND.search(str(handler.get("command", ""))) if isinstance(handler, dict) else None
                if m:
                    found.add(m.group(1))
    return found, None


def claude_plugin_enabled():
    """True or False from Claude Code's settings.json `enabledPlugins`; None when it cannot be told."""
    try:
        with open(os.path.join(gwsessions.claude_dir(), "settings.json"), encoding="utf-8") as f:
            enabled = json.load(f).get("enabledPlugins")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(enabled, dict):
        return None
    mine = [v for k, v in enabled.items() if str(k).startswith("whatsnext@")]
    return any(mine) if mine else None


def last_fired(root):
    """(event, UTC time) of the newest `last_event` in `.whatsnext/sessions/<id>.json`, or None."""
    best = None
    for path in glob.glob(os.path.join(glob.escape(os.path.join(root, gwjournal.SESSIONS_DIR)), "*.json")):
        if path.count(".") > 1 and not path.endswith(".json"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(state, dict) and isinstance(state.get("last_event_time"), str) and state.get("last_event"):
            if best is None or state["last_event_time"] > best[1]:
                best = (state["last_event"], state["last_event_time"])
    return best


def codex_gaps(root):
    """[(scope, shown path, events to fix, error)] for the user and project hooks files that hold whatsnext's
    entries. A file with none of them is reported once, as not installed."""
    out = []
    for scope in ("user", "project"):
        result = gwhooksinstall.plan(scope, False, root=root)
        has_own = bool(result["old"]) and "whatsnext.py" in result["old"] and "--agent codex" in result["old"]
        out.append((scope, result["shown"], result["events"], result["error"], has_own))
    return out


def report(root):
    """{"agents": {...}, "lines": [...], "gaps": n}. The lines are what `doctor` prints."""
    lines, gaps = [], 0

    lines.append("Claude Code")
    found, error = claude_hooks()
    missing = [e for e in CLAUDE_EVENTS if e not in found]
    if error:
        gaps += 1
        lines += ["  hooks: %s" % error, "  fix: reinstall the whatsnext plugin"]
    elif missing:
        gaps += 1
        lines += ["  hooks: missing %s in the plugin's hooks/hooks.json" % ", ".join(missing),
                  "  fix: update the whatsnext plugin"]
    else:
        lines.append("  hooks: all %d events are in the plugin's hooks/hooks.json" % len(CLAUDE_EVENTS))
    enabled = claude_plugin_enabled()
    if enabled is False:
        gaps += 1
        lines += ["  plugin: installed but disabled", "  fix: enable the whatsnext plugin in Claude Code (/plugin)"]
    elif enabled is None:
        lines.append("  plugin: not checked (no whatsnext entry in settings.json enabledPlugins)")
    else:
        lines.append("  plugin: enabled")

    lines.append("Codex")
    user = project = None
    for scope, shown, events, err, has_own in codex_gaps(root):
        if err:
            gaps += 1
            lines += ["  hooks (%s): %s" % (scope, err)]
        elif has_own and events:
            gaps += 1
            lines += ["  hooks (%s, %s): missing or changed: %s" % (scope, shown, ", ".join(events)),
                      "  fix: whatsnext install-hooks --%s" % scope]
        elif has_own:
            lines.append("  hooks (%s, %s): all %d events installed" % (scope, shown, len(gwhooksinstall.EVENTS)))
        if scope == "user":
            user = has_own
        else:
            project = has_own
    if not user and not project:
        gaps += 1
        lines += ["  hooks: not installed", "  fix: whatsnext install-hooks --user"]
    lines.append("  trust: Codex skips new or changed hooks until you trust them. Open /hooks in Codex; "
                 "whatsnext cannot check this.")

    lines.append("PreCompact text: Claude Code yes, Codex no (ignored; Codex gets the journal fact and the resume note)")
    fired = last_fired(root)
    lines.append("Last hook fired (either agent): %s" % ("%s at %s" % fired if fired else "none recorded yet"))
    return {"lines": lines, "gaps": gaps, "last_fired": fired}


def run(argv):
    if set(argv) - {"--json"}:
        print("usage: whatsnext doctor [--json]", file=sys.stderr)
        return 2
    result = report(gwconfig.find_root())
    if "--json" in argv:
        print(json.dumps(result, indent=2))
    else:
        print("whatsnext doctor")
        for line in result["lines"]:
            print(line)
        print("%s." % ("No gaps found" if not result["gaps"] else "%d gap%s found" % (result["gaps"], "" if result["gaps"] == 1 else "s")))
    return 1 if result["gaps"] else 0
