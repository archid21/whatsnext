"""`whatsnext install-hooks`: whatsnext's hooks for Codex (ADR-0005).

Writes `hooks.json` next to a
Codex config layer: `~/.codex/hooks.json` (--user, the default) or
`<repo>/.codex/hooks.json` (--project). Codex merges hooks from every layer, so these
entries sit beside the user's own; only entries whose command is
`... whatsnext.py hook <event> --agent codex` count as whatsnext's.

Codex has no plan-mode signal in UserPromptSubmit (live test C),
so only SessionStart, Stop and PreCompact are installed. Idempotent, keeps every other
hook and key, `--dry-run` prints the diff and writes nothing, `--remove` takes out
whatsnext's entries only. Codex skips a new or changed hook until the user trusts it.

Codex has no plugin loader that finds `<plugin>/skills/`, so the user scope also links the
skill folder into `~/.agents/skills/whatsnext` (a symlink to this plugin's `skills/whatsnext`).
It never replaces a file, folder or link it did not make; `--remove` removes only its own link.
"""

import argparse
import difflib
import json
import os
import re
import sys

from . import config as gwconfig

# Codex event -> (whatsnext event, matcher or None, timeout in seconds, additionalContextLimit or None).
EVENTS = (
    ("SessionStart", "session-start", "startup|resume|clear|compact", 10, 5000),
    ("Stop", "stop", None, 10, None),
    ("PreCompact", "pre-compact", None, 10, None),
)
AGENT = "codex"
OWN_COMMAND = re.compile(r"whatsnext\.py[\"']?\s+hook\s+\S+\s+--agent\s+codex\b")
TRUST_NOTE = "Next: in Codex, open /hooks and trust the whatsnext hooks. Codex skips new or changed hooks until you do."


def home():
    return os.environ.get("HOME") or os.path.expanduser("~")


def codex_dir():
    return os.environ.get("CODEX_HOME") or os.path.join(home(), ".codex")


def script_path():
    """Absolute path of whatsnext.py (the script that is running)."""
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "whatsnext.py"))


def skill_target():
    """The skill folder of this plugin: <plugin>/skills/whatsnext."""
    return os.path.dirname(os.path.dirname(script_path()))


def skill_link():
    return os.path.join(home(), ".agents", "skills", "whatsnext")


def skill_plan(remove):
    """(action, path, message): action is 'link', 'unlink', 'keep' or 'skip'. Writes nothing."""
    path, target = skill_link(), skill_target()
    shown = "~/.agents/skills/whatsnext"
    if os.path.islink(path):
        current = os.readlink(path)
        mine = os.path.realpath(path) == os.path.realpath(target) or (
            not os.path.exists(path) and current.rstrip("/").endswith(os.path.join("skills", "whatsnext")))
        if not mine:
            return "skip", path, "%s is a link to %s, not whatsnext's skill; left as it is" % (shown, current)
        if remove:
            return "unlink", path, "remove the skill link %s" % shown
        if os.path.realpath(path) == os.path.realpath(target):
            return "keep", path, "the skill link %s is already in place" % shown
        return "relink", path, "repoint the skill link %s to %s" % (shown, target)
    if os.path.exists(path):
        return "skip", path, "%s exists and is not a link; left as it is" % shown
    if remove:
        return "keep", path, ""
    return "link", path, "link the skill: %s -> %s" % (shown, target)


def apply_skill(action, path):
    if action in ("unlink", "relink"):
        os.remove(path)
    if action in ("link", "relink"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(skill_target(), path)


def quote(path):
    """`path` in double quotes for a shell, with the four characters that stay special there escaped."""
    return '"%s"' % re.sub(r'(["\\$`])', r"\\\1", path)


def handler_for(spec, script):
    _codex_event, event, _matcher, timeout, limit = spec
    handler = {"type": "command", "command": "python3 %s hook %s --agent %s" % (quote(script), event, AGENT),
               "timeout": timeout}
    if limit:
        handler["additionalContextLimit"] = limit
    return handler


def is_own(handler):
    return isinstance(handler, dict) and isinstance(handler.get("command"), str) and bool(
        OWN_COMMAND.search(handler["command"]))


def without_own(groups):
    """`groups` without whatsnext's handlers; a group left with no handler is dropped."""
    out = []
    for group in groups:
        handlers = group.get("hooks", [])
        kept = [h for h in handlers if not is_own(h)]
        if len(kept) == len(handlers):
            out.append(group)
        elif kept:
            out.append(dict(group, hooks=kept))
    return out


def install_event(groups, spec, script):
    """The groups for one event with whatsnext's entry in place (an exact match leaves the list as it is)."""
    want = {"hooks": [handler_for(spec, script)]}
    if spec[2]:
        want = dict([("matcher", spec[2])], **want)
    own = [g for g in groups if any(is_own(h) for h in g.get("hooks", []))]
    if own == [want]:
        return groups
    return without_own(groups) + [want]


def scope_file(scope, root):
    """(path, shown) of the hooks.json for a scope."""
    if scope == "project":
        return os.path.join(root, ".codex", "hooks.json"), ".codex/hooks.json"
    path = os.path.join(codex_dir(), "hooks.json")
    prefix = os.path.join(home(), "")
    return path, ("~/" + path[len(prefix):]) if path.startswith(prefix) else path


def read_doc(path, shown):
    """(data, old text, error)."""
    try:
        with open(path, encoding="utf-8") as f:
            old = f.read()
    except FileNotFoundError:
        return {}, "", None
    except OSError as e:
        return None, "", "%s: %s" % (shown, e.strerror or e)
    if not old.strip():
        return {}, old, None
    try:
        data = json.loads(old)
    except ValueError as e:
        return None, old, "%s: not valid JSON (%s); fix it first, install-hooks left it unchanged" % (shown, e)
    if not isinstance(data, dict):
        return None, old, "%s: not a JSON object; fix it first, install-hooks left it unchanged" % shown
    return data, old, None


def plan(scope, remove, script=None, root=None):
    """The change as a dict: path, shown, old, new text, events, error. Writes nothing."""
    script = script or script_path()
    root = root or gwconfig.find_root()
    path, shown = scope_file(scope, root)
    data, old, error = read_doc(path, shown)
    out = {"scope": scope, "path": path, "shown": shown, "old": old, "new": old, "events": [], "error": error}
    if error:
        return out
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        out["error"] = "%s: hooks is not an object; fix it first, install-hooks left it unchanged" % shown
        return out
    for spec in EVENTS:
        groups = hooks.get(spec[0], [])
        if not isinstance(groups, list) or not all(isinstance(g, dict) and isinstance(g.get("hooks", []), list)
                                                   for g in groups):
            out["error"] = "%s: hooks.%s is not a list of matcher groups; fix it first" % (shown, spec[0])
            return out
    hooks = json.loads(json.dumps(hooks))  # a copy
    for spec in EVENTS:
        groups = hooks.get(spec[0], [])
        new = without_own(groups) if remove else install_event(groups, spec, script)
        if new != groups:
            out["events"].append(spec[0])
            if new:
                hooks[spec[0]] = new
            else:
                hooks.pop(spec[0], None)
    if out["events"]:
        data = dict(data)
        if hooks:
            data["hooks"] = hooks
        else:
            data.pop("hooks", None)
        out["new"] = json.dumps(data, indent=2, ensure_ascii=False) + "\n" if data else ""
    return out


def diff(result):
    return "".join(difflib.unified_diff(result["old"].splitlines(True), result["new"].splitlines(True),
                                        result["shown"], result["shown"]))


def apply(result):
    path = result["path"]
    if not result["new"]:  # nothing else was in the file: take it away
        os.remove(path)
        if result["scope"] == "project":  # never the user's own Codex folder
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(result["new"])


def build_parser():
    parser = argparse.ArgumentParser(prog="whatsnext install-hooks",
                                     description="Install whatsnext's hooks for Codex (hooks.json).")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--user", action="store_true", help="~/.codex/hooks.json (the default)")
    where.add_argument("--project", action="store_true", help="<repo>/.codex/hooks.json")
    parser.add_argument("--dry-run", action="store_true", help="print the change; write nothing")
    parser.add_argument("--remove", action="store_true", help="take out whatsnext's entries only")
    return parser


def run(argv, script=None, root=None):
    args = build_parser().parse_args(argv)
    scope = "project" if args.project else "user"
    if scope == "user" and not args.remove and not os.path.isdir(codex_dir()):
        print("Codex folder not found: %s. Install Codex first, or use --project." % codex_dir(), file=sys.stderr)
        return 1
    result = plan(scope, args.remove, script=script, root=root)
    if result["error"]:
        print(result["error"], file=sys.stderr)
        return 1
    skill = skill_plan(args.remove) if scope == "user" else ("keep", None, "")
    skill_changes = skill[0] in ("link", "unlink", "relink")
    if not result["events"] and not skill_changes:
        print("Nothing to change in %s: %s." % (result["shown"], "no whatsnext hooks there" if args.remove
                                                else "the whatsnext hooks are already installed"))
        if skill[0] == "skip":
            print("Skill: " + skill[2] + ".")
        return 0
    if result["events"]:
        print("%s whatsnext hooks for Codex in %s (%s)" % ("Remove" if args.remove else "Install", result["shown"],
                                                          ", ".join(result["events"])))
        print(diff(result), end="")
    if skill[2]:
        print(("Skill: " if skill[0] == "skip" else "") + (("would " if args.dry_run and skill_changes else "") + skill[2]))
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    if result["events"]:
        apply(result)
        print("Removed %s (nothing else was in it)." % result["shown"] if not result["new"]
              else "Written: %s" % result["shown"])
    if skill_changes:
        apply_skill(skill[0], skill[1])
        print("Skill link %s." % ("removed" if skill[0] == "unlink" else "written"))
    if scope == "project" and not args.remove:
        print("Note: Codex loads project hooks only when this project's .codex/ folder is trusted.")
    if not args.remove:
        if result["events"]:
            print(TRUST_NOTE)
    return 0
