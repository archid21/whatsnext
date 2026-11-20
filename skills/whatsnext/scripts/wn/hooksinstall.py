"""`whatsnext install-hooks`: whatsnext's hooks for Codex, Gemini CLI and Cursor (ADR-0005, ADR-0027).

`--agent codex|gemini|cursor` (default codex) picks the adapter. Gemini CLI: `~/.gemini/settings.json` or
`<repo>/.gemini/settings.json` (a `hooks` key in the settings file; timeouts in milliseconds). Cursor:
`~/.cursor/hooks.json` or `<repo>/.cursor/hooks.json` (`version: 1`, a flat handler list per event; timeouts in
seconds). Each agent's events are listed in its table below, with the doc page they come from. Everything below
about Codex holds for the other two: the entries are recognised by their command, and nothing else is touched.

Writes `hooks.json` next to a
Codex config layer: `~/.codex/hooks.json` (--user, the default) or
`<repo>/.codex/hooks.json` (--project). Codex merges hooks from every layer, so these
entries sit beside the user's own; only entries whose command is
`... whatsnext.py hook <event> --agent codex` count as whatsnext's.

Codex plan capture reads the transcript at Stop; UserPromptSubmit handles wrap-up and compact resume. Idempotent, keeps every other
hook and key, `--dry-run` prints the diff and writes nothing, `--remove` takes out
whatsnext's entries only. Codex skips a new or changed hook until the user trusts it.

This checkout installer does not depend on native plugin packaging; the user scope links the
skill folder into `~/.agents/skills/whatsnext` (a symlink to this plugin's `skills/whatsnext`).
It never replaces a file, folder or link it did not make; `--remove` removes only its own link.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import time

from . import config as gwconfig
from .ask import ask, option

# Codex event -> (whatsnext event, matcher or None, timeout in seconds, additionalContextLimit or None).
EVENTS = (
    ("SessionStart", "session-start", "startup|resume|clear|compact|fork", 10, 5000),
    ("Stop", "stop", None, 10, None),
    ("PreCompact", "pre-compact", None, 10, None),
    ("PreToolUse", "pre-edit", "apply_patch|Edit|Write", 10, None),  # warns on a hand-ticked PLAN.md item (P-7)
    ("UserPromptSubmit", "prompt-submit", None, 10, None),  # prints the resume note once after a compact (P-22)
    ("SessionEnd", "session-end", None, 3, None),
    ("Interrupt", "interrupt", None, 3, None),
)
AGENT = "codex"
OWN_COMMAND = re.compile(r"whatsnext\.py[\"']?\s+hook\s+\S+\s+--agent\s+codex\b")
TRUST_NOTE = "Next: in Codex, open /hooks and trust the whatsnext hooks. Codex skips new or changed hooks until you do."

# Gemini CLI event -> (whatsnext event, matcher, timeout in MILLISECONDS, None). https://geminicli.com/docs/hooks/
# Gemini's PreCompress and SessionEnd print nothing back to the model; they only record the facts. Not mapped:
# BeforeTool (the plan-tick guard) is outside P-77.
GEMINI_EVENTS = (
    ("SessionStart", "session-start", "*", 10000, None),
    ("BeforeAgent", "prompt-submit", "*", 10000, None),
    ("AfterAgent", "stop", "*", 10000, None),
    ("PreCompress", "pre-compact", "*", 10000, None),
    ("SessionEnd", "session-end", "*", 3000, None),
)
# Cursor event -> (whatsnext event, matcher, timeout in SECONDS, None). https://cursor.com/docs/hooks
# No `prompt-submit`: Cursor's beforeSubmitPrompt can only allow or block a prompt, it cannot add text to it, so it
# could neither carry the `wrap up` instructions nor a resume note. That gap is recorded in P-77's progress file.
CURSOR_EVENTS = (
    ("sessionStart", "session-start", None, 10, None),
    ("stop", "stop", None, 10, None),
    ("preCompact", "pre-compact", None, 10, None),
    ("sessionEnd", "session-end", None, 3, None),
)


class Adapter:
    """One agent's hook file: where it is, how its JSON is shaped, which events it maps."""

    def __init__(self, name, label, events, folder, dirname, filename, flat=False, base=None, trust=None, project_note=None):
        self.name, self.label, self.events, self.folder, self.dirname, self.filename = name, label, events, folder, dirname, filename
        self.flat = flat  # Cursor: hooks.<event> is a list of handlers; others: a list of matcher groups
        self.base = base or {}  # keys the file needs besides `hooks` (Cursor: version 1)
        self.trust, self.project_note = trust, project_note
        self.own = re.compile(r"whatsnext\.py[\"']?\s+hook\s+\S+\s+--agent\s+%s\b" % re.escape(name))


def gemini_dir():
    return os.path.join(home(), ".gemini")


def cursor_dir():
    return os.path.join(home(), ".cursor")


def adapters():
    return {
        "codex": Adapter("codex", "Codex", EVENTS, codex_dir, ".codex", "hooks.json", trust=TRUST_NOTE,
                         project_note="Note: Codex loads project hooks only when this project's .codex/ folder is trusted."),
        "gemini": Adapter("gemini", "Gemini CLI", GEMINI_EVENTS, gemini_dir, ".gemini", "settings.json",
                          trust="Next: in Gemini CLI, run /hooks panel to see the whatsnext hooks. "
                                "Hooks run only while hooksConfig.enabled is true (the default)."),
        "cursor": Adapter("cursor", "Cursor", CURSOR_EVENTS, cursor_dir, ".cursor", "hooks.json", flat=True,
                          base={"version": 1},
                          trust="Next: Cursor reloads hooks.json when it is saved; restart Cursor if the hooks do not load.",
                          project_note="Note: Cursor runs project hooks only in a trusted workspace."),
    }


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


def wn_link():
    return os.path.join(home(), ".local", "bin", "wn")


def wn_plan(remove):
    """(action, path, message): action is 'link', 'unlink', 'keep' or 'skip'. Writes nothing."""
    path, target = wn_link(), script_path()
    shown = "~/.local/bin/wn"
    if os.path.islink(path):
        current = os.readlink(path)
        mine = os.path.realpath(path) == os.path.realpath(target) or (
            os.path.abspath(os.path.join(os.path.dirname(path), current)) == target)
        if not mine:
            return "skip", path, "%s is a link to %s, not whatsnext.py; left as it is" % (shown, current)
        if remove:
            return "unlink", path, "remove the wn link %s" % shown
        return "keep", path, "the wn link %s is already in place" % shown
    if os.path.exists(path):
        return "skip", path, "%s exists and is not a link; left as it is" % shown
    if remove:
        return "keep", path, ""
    return "link", path, "link wn: %s -> %s" % (shown, target)


def apply_wn(action, path):
    if action == "unlink":
        os.remove(path)
    if action == "link":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(script_path(), path)


def on_path(folder):
    real = os.path.realpath(folder)
    return any(p and os.path.realpath(p) == real for p in os.environ.get("PATH", "").split(os.pathsep))


def quote(path):
    """`path` in double quotes for a shell, with the four characters that stay special there escaped."""
    return '"%s"' % re.sub(r'(["\\$`])', r"\\\1", path)


def handler_for(spec, script, ad=None):
    ad = ad or adapters()[AGENT]
    _agent_event, event, _matcher, timeout, limit = spec
    handler = {"type": "command", "command": "python3 %s hook %s --agent %s" % (quote(script), event, ad.name),
               "timeout": timeout}
    if ad.name == "codex":  # Codex shows statusMessage as the hook's title in /hooks ("Unnamed hook" without it)
        handler["statusMessage"] = "whatsnext: " + event
    if ad.name == "gemini":  # Gemini names a hook for its logs and `/hooks enable|disable <name>`
        handler = dict([("name", "whatsnext-" + event)], **handler)
    if ad.flat and spec[2]:
        handler["matcher"] = spec[2]
    if limit:
        handler["additionalContextLimit"] = limit
    return handler


def is_own(handler, ad=None):
    own = (ad or adapters()[AGENT]).own
    return isinstance(handler, dict) and isinstance(handler.get("command"), str) and bool(own.search(handler["command"]))


def without_own(groups, ad=None):
    """`groups` without whatsnext's handlers; a group left with no handler is dropped."""
    ad = ad or adapters()[AGENT]
    if ad.flat:
        return [h for h in groups if not is_own(h, ad)]
    out = []
    for group in groups:
        handlers = group.get("hooks", [])
        kept = [h for h in handlers if not is_own(h, ad)]
        if len(kept) == len(handlers):
            out.append(group)
        elif kept:
            out.append(dict(group, hooks=kept))
    return out


def install_event(groups, spec, script, ad=None):
    """The groups for one event with whatsnext's entry in place (an exact match leaves the list as it is)."""
    ad = ad or adapters()[AGENT]
    if ad.flat:
        want = handler_for(spec, script, ad)
        own = [h for h in groups if is_own(h, ad)]
        return groups if own == [want] else without_own(groups, ad) + [want]
    want = {"hooks": [handler_for(spec, script, ad)]}
    if spec[2]:
        want = dict([("matcher", spec[2])], **want)
    own = [g for g in groups if any(is_own(h, ad) for h in g.get("hooks", []))]
    if own == [want]:
        return groups
    if own:  # replace in place: Codex keys hook trust by group index, so keep the position
        at = groups.index(own[0])
        rest = without_own(groups, ad)
        kept_before = len(without_own(groups[:at], ad))
        return rest[:kept_before] + [want] + rest[kept_before:]
    return groups + [want]


def scope_file(scope, root, ad=None):
    """(path, shown) of the hook file for a scope."""
    ad = ad or adapters()[AGENT]
    if scope == "project":
        return os.path.join(root, ad.dirname, ad.filename), "%s/%s" % (ad.dirname, ad.filename)
    path = os.path.join(ad.folder(), ad.filename)
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


def plan(scope, remove, script=None, root=None, agent=AGENT):
    """The change as a dict: path, shown, old, new text, events, error. Writes nothing."""
    ad = adapters()[agent]
    script = script or script_path()
    root = root or gwconfig.find_root()
    path, shown = scope_file(scope, root, ad)
    data, old, error = read_doc(path, shown)
    out = {"scope": scope, "path": path, "shown": shown, "old": old, "new": old, "events": [], "error": error,
           "agent": agent}
    if error:
        return out
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        out["error"] = "%s: hooks is not an object; fix it first, install-hooks left it unchanged" % shown
        return out
    for spec in ad.events:
        groups = hooks.get(spec[0], [])
        if ad.flat:
            ok = isinstance(groups, list) and all(isinstance(h, dict) for h in groups)
        else:
            ok = isinstance(groups, list) and all(isinstance(g, dict) and isinstance(g.get("hooks", []), list)
                                                  for g in groups)
        if not ok:
            out["error"] = "%s: hooks.%s is not a list of %s; fix it first" % (
                shown, spec[0], "hook handlers" if ad.flat else "matcher groups")
            return out
    hooks = json.loads(json.dumps(hooks))  # a copy
    for spec in ad.events:
        groups = hooks.get(spec[0], [])
        new = without_own(groups, ad) if remove else install_event(groups, spec, script, ad)
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
            for key, value in ad.base.items():  # Cursor needs `version`, first in the file
                if key not in data:
                    data = dict([(key, value)], **data)
        else:
            data.pop("hooks", None)
        empty = not data or (remove and data == ad.base)  # a bare `{"version": 1}` is no entry of anyone's
        out["new"] = "" if empty else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return out


def diff(result):
    return "".join(difflib.unified_diff(result["old"].splitlines(True), result["new"].splitlines(True),
                                        result["shown"], result["shown"]))


def backup_dir():
    """Where install-hooks keeps a copy of each file before it changes it (P-90): beside the user config."""
    return os.path.join(os.path.dirname(gwconfig.user_config_path()), "backups")


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_manifest():
    try:
        with open(os.path.join(backup_dir(), "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_manifest(data):
    os.makedirs(backup_dir(), exist_ok=True)
    tmp = os.path.join(backup_dir(), "manifest.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(backup_dir(), "manifest.json"))


def save_backup(result, now=None):
    """Copy the file's current bytes to the backup folder before an install writes it; return the backup path
    (None when the file did not exist). The manifest remembers the backup and a hash of the text we write, so
    --undo can tell whether the file was changed after the install."""
    path = result["path"]
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    backup = None
    if os.path.exists(path):
        os.makedirs(backup_dir(), exist_ok=True)
        name = "%s-%s-%s-%s" % (result.get("agent", AGENT), result["scope"],
                                hashlib.sha256(path.encode("utf-8")).hexdigest()[:8], stamp)
        backup = os.path.join(backup_dir(), name + os.path.splitext(path)[1])
        n = 1
        while os.path.exists(backup):
            n += 1
            backup = os.path.join(backup_dir(), "%s-%d%s" % (name, n, os.path.splitext(path)[1]))
        shutil.copy2(path, backup)
    manifest = read_manifest()
    entry = manifest.get(path) if isinstance(manifest.get(path), dict) else None
    if entry is None or entry.get("written") is None:  # keep the first original: a reinstall must not overwrite it
        entry = {"backup": backup, "existed": backup is not None}
    entry["written"] = text_hash(result["new"])
    entry["when"] = stamp
    manifest[path] = entry
    write_manifest(manifest)
    return backup


def restore_plan(path):
    """For --undo: the manifest entry when the file is still exactly what install-hooks wrote, else None."""
    entry = read_manifest().get(path)
    if not isinstance(entry, dict) or not entry.get("written"):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            current = f.read()
    except OSError:
        return None
    if text_hash(current) != entry["written"]:
        return None
    if entry.get("existed") and not (entry.get("backup") and os.path.isfile(entry["backup"])):
        return None
    return entry


def restore(path, entry):
    """Put the original back byte for byte (or remove the file when there was none), and forget the entry."""
    if entry.get("existed"):
        shutil.copy2(entry["backup"], path)
    else:
        os.remove(path)
    manifest = read_manifest()
    manifest.pop(path, None)
    write_manifest(manifest)


def forget(path):
    manifest = read_manifest()
    if path in manifest:
        manifest[path]["written"] = None  # changed since: undo removed only our entries; the backup stays
        write_manifest(manifest)


def apply(result):
    path = result["path"]
    if not result["new"]:  # nothing else was in the file: take it away
        os.remove(path)
        if result["scope"] == "project":  # never the user's own agent folder
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
                                     description="Install whatsnext's hooks for Codex (default), Gemini CLI or Cursor.")
    parser.add_argument("--agent", choices=("codex", "gemini", "cursor"), default=AGENT,
                        help="which agent's hook file to write (default: codex)")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--user", action="store_true", help="the agent's user file, e.g. ~/.codex/hooks.json (the default)")
    where.add_argument("--project", action="store_true", help="the agent's project file, e.g. <repo>/.codex/hooks.json")
    parser.add_argument("--dry-run", action="store_true", help="print the change; write nothing")
    parser.add_argument("--remove", "--undo", dest="remove", action="store_true",
                        help="take out whatsnext's entries only (also the wn link)")
    parser.add_argument("--wn", choices=("link", "skip"), help="user scope: link ~/.local/bin/wn to whatsnext.py, or not")
    parser.add_argument("--json", action="store_true", help="print a question as JSON")
    return parser


def run(argv, script=None, root=None):
    args = build_parser().parse_args(argv)
    scope = "project" if args.project else "user"
    ad = adapters()[args.agent]
    no_codex = scope == "user" and not args.remove and not os.path.isdir(ad.folder())
    if no_codex:  # still offer the wn link; the agent's hooks need the agent
        print("%s folder not found: %s. Skipping the %s hooks; install %s first, or use --project."
              % (ad.label, ad.folder(), ad.label, ad.label))
        result = {"events": [], "error": None, "shown": ad.folder(), "new": None}
    else:
        result = plan(scope, args.remove, script=script, root=root, agent=args.agent)
    if result["error"]:
        print(result["error"], file=sys.stderr)
        return 1
    skill = skill_plan(args.remove) if scope == "user" and not no_codex else ("keep", None, "")
    skill_changes = skill[0] in ("link", "unlink", "relink")
    wn = wn_plan(args.remove) if scope == "user" else ("keep", None, "")
    if wn[0] == "link" and args.wn == "skip":
        wn = ("keep", None, "")
    wn_changes = wn[0] in ("link", "unlink")
    if wn[0] == "link" and not args.wn and not args.dry_run:
        return ask(args.json, "wn_link",
                   "Link `wn` to whatsnext, so agents can run `wn status` from any folder? "
                   "It makes %s -> %s." % (wn_link(), script_path()),
                   options=[option("link", "Link wn", "make the link"), option("skip", "Skip", "no link")],
                   recommended="link", answer="--wn link|skip")
    if not result["events"] and not skill_changes and not wn_changes:
        print("Nothing to change in %s: %s." % (result["shown"], "no whatsnext hooks there" if args.remove
                                                else "the whatsnext hooks are already installed"))
        if skill[0] == "skip":
            print("Skill: " + skill[2] + ".")
        if wn[0] == "skip":
            print("wn: " + wn[2] + ".")
        return 0
    if result["events"]:
        print("%s whatsnext hooks for %s in %s (%s)" % ("Remove" if args.remove else "Install", ad.label,
                                                       result["shown"], ", ".join(result["events"])))
        print(diff(result), end="")
    if skill[2]:
        print(("Skill: " if skill[0] == "skip" else "") + (("would " if args.dry_run and skill_changes else "") + skill[2]))
    if wn[2] and (wn_changes or wn[0] == "skip"):
        print(("wn: " if wn[0] == "skip" else "") + (("would " if args.dry_run and wn_changes else "") + wn[2]))
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    if result["events"] and args.remove:
        entry = restore_plan(result["path"])
        if entry:
            restore(result["path"], entry)
            if not entry.get("existed") and result["scope"] == "project":  # as apply: take the empty folder away
                try:
                    os.rmdir(os.path.dirname(result["path"]))
                except OSError:
                    pass
            print("Restored %s from its backup, byte for byte." % result["shown"] if entry.get("existed")
                  else "Removed %s (install-hooks created it)." % result["shown"])
        else:
            backup = (read_manifest().get(result["path"]) or {}).get("backup")
            apply(result)
            forget(result["path"])
            print("Removed %s (nothing else was in it)." % result["shown"] if not result["new"]
                  else "Written: %s (only whatsnext's entries removed)" % result["shown"])
            if backup and os.path.isfile(backup):
                print("The file changed after the install, so it was not restored whole. Original copy: %s" % backup)
    elif result["events"]:
        backup = save_backup(result)
        apply(result)
        print("Written: %s" % result["shown"])
        if backup:
            print("Backup of the previous file: %s" % backup)
    if skill_changes:
        apply_skill(skill[0], skill[1])
        print("Skill link %s." % ("removed" if skill[0] == "unlink" else "written"))
    if wn_changes:
        apply_wn(wn[0], wn[1])
        print("wn link %s." % ("removed" if wn[0] == "unlink" else "written"))
        if wn[0] == "link" and not on_path(os.path.dirname(wn[1])):
            print("Add ~/.local/bin to your PATH so `wn` is found.")
    if scope == "project" and not args.remove and ad.project_note:
        print(ad.project_note)
    if not args.remove:
        if result["events"] and ad.trust:
            print(ad.trust)
    return 0
