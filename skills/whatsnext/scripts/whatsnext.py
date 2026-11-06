#!/usr/bin/env python3
"""whatsnext: one entry point for the plan, check-offs and task progress.

Python 3.9+, standard library only. Commands: `plan`, `progress`,
`config show` and `config set --user`, `init`, `install-hooks` (Codex), `compact-instructions`
and `hook` (called by the agents' hook configs, ADR-0005). A hook must never break a session: on any error it prints nothing and exits 0.
"""

import argparse
import contextlib
import io
import json
import os
import sys

# Make the wn package importable however the script is started.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VERSION = "0.1.0"

# Subcommands and a one-line description of each.
COMMANDS = {
    "plan": "the plan checklist: list, next, start, check off, put back",
    "progress": "task progress files, plan capture and the resume note",
    "config": "show the effective settings (config show) or set one in the user layer (config set --user <key> <value>)",
    "init": "adopt whatsnext in a git repository (--dry-run, --undo)",
    "install-hooks": "install the whatsnext hooks for Codex (hooks.json)",
    "doctor": "check that the hooks are in place for Claude Code and Codex, and when one last fired",
    "compact-instructions": "print the text for `/compact` in an open session (ADR-0009)",
}

# Hook events and the agents a hook may name with `--agent` (ADR-0005).
HOOK_EVENTS = ("session-start", "plan-shown", "plan-approved", "prompt-submit", "stop", "pre-compact", "post-compact", "session-end")
HOOK_AGENTS = ("claude-code", "codex")


def config_show(args):
    """Print every effective setting with its source layer."""
    from wn import config as wnconfig

    effective = wnconfig.load()
    for message in effective.errors:
        print(message, file=sys.stderr)
    keys = sorted(effective.entries)
    if "--json" in args:
        out = {}
        for key in keys:
            entry = effective.entries[key]
            out[key] = {"value": entry.value, "source": entry.source, "file": entry.file}
        print(json.dumps(out, indent=2))
    else:
        for key in keys:
            entry = effective.entries[key]
            source = entry.source if entry.file is None else "%s: %s" % (entry.source, entry.file)
            print("%s = %s  (%s)" % (key, json.dumps(entry.value), source))
    return 1 if effective.errors else 0


def config_set(args):
    """`config set --user <key> <value>`: write one setting to the user layer, then print its effective value."""
    from wn import config as wnconfig

    if len(args) != 3 or args[0] != "--user":
        print("usage: whatsnext config set --user <key> <value>", file=sys.stderr)
        return 2
    try:
        wnconfig.set_user(args[1], args[2])
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    except OSError as e:
        print("Could not write %s: %s" % (wnconfig.user_config_path(), e), file=sys.stderr)
        return 1
    effective = wnconfig.load()
    for message in effective.errors:
        print(message, file=sys.stderr)
    entry = effective.entries[args[1]]
    source = entry.source if entry.file is None else "%s: %s" % (entry.source, entry.file)
    print("%s = %s  (%s)" % (args[1], json.dumps(entry.value), source))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="whatsnext", description="A shared plan, check-off and resumable task progress for every coding agent in a project.")
    parser.add_argument("--version", action="version", version="whatsnext " + VERSION)
    sub = parser.add_subparsers(dest="command")
    for name, help_text in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        p.add_argument("args", nargs=argparse.REMAINDER)
    hook = sub.add_parser("hook", help="run a hook event (called by agent hook configs)")
    hook.add_argument("event", choices=HOOK_EVENTS)
    hook.add_argument("--agent", choices=HOOK_AGENTS, help="the agent that runs the hook")
    return parser


def run_hook(event, agent=None):
    from wn import hook as wnhook

    with contextlib.redirect_stderr(io.StringIO()):
        text = wnhook.handle(event, wnhook.read_input(sys.stdin), agent)
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()
    return 0


def main(argv=None):
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in COMMANDS:
        # argparse.REMAINDER drops the rest when it starts with an option (`plan --json`).
        args = argparse.Namespace(command=argv[0], args=argv[1:])
    elif argv and argv[0] == "hook":
        # A hook must never break the session, and Codex reads exit 2 as "block": a bad argument is silent, exit 0.
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                args = parser.parse_args(argv)
        except SystemExit:
            return 0
        try:
            return run_hook(args.event, args.agent)
        except Exception:  # a hook must never break the agent's session
            return 0
    else:
        args = parser.parse_args(argv)
    if args.command == "config":
        if args.args and args.args[0] == "show" and set(args.args[1:]) <= {"--json"}:
            return config_show(args.args[1:])
        if args.args and args.args[0] == "set":
            return config_set(args.args[1:])
        print("usage: whatsnext config show [--json] | config set --user <key> <value>", file=sys.stderr)
        return 2
    if args.command == "plan":
        from wn import plan as wnplan

        return wnplan.run(args.args)
    if args.command == "progress":
        from wn import status as wnstatus

        return wnstatus.run(args.args)
    if args.command == "init":
        from wn import initcmd as wninitcmd

        return wninitcmd.run(args.args)
    if args.command == "compact-instructions":
        from wn import compact as wncompact

        return wncompact.cmd_instructions(args.args)
    if args.command == "doctor":
        from wn import doctor as wndoctor

        return wndoctor.run(args.args)
    if args.command == "install-hooks":
        from wn import hooksinstall as wnhooksinstall

        return wnhooksinstall.run(args.args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
