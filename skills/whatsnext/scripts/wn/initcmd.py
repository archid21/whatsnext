"""`whatsnext init`: adopt whatsnext in a git repository (ADR-0007, slice 1, git mode only).

Additive: it creates only what is missing and never overwrites a file. It owns five things: the plan
file (`paths.plan`), `.whatsnext/config.json`, the progress folder with its journal folder, the
`.whatsnext/sessions/` line in `.gitignore`, and one marked block in `AGENTS.md` (appended, never replacing or reordering text). It prints where the
plugin's hooks are instead of installing them. `--dry-run` prints the plan and writes nothing;
`--undo` removes only the marked block.

Not in this slice: the first progress file captured from git history and the "what are you in the
middle of?" question (decision 11 item 2), plan import (item 1), CLAUDE.md, .gitattributes, agent
hook settings (item 4) and folder mode (outside git).
"""

import argparse
import os
import sys

from . import config as gwconfig
from . import status as gwstatus

START = "<!-- whatsnext:start -->"
END = "<!-- whatsnext:end -->"
AGENTS = "AGENTS.md"
CONFIG_REL = os.path.join(".whatsnext", "config.json")
CONFIG_TEXT = "{}\n"

PLAN_TEMPLATE = """# Plan

One line per item: `- [ ] P-N Title · done means: <how we know it is done>`.

## Now

## Next

## Later
"""


def block_lines(plan_rel, progress_rel):
    """The AGENTS.md protocol block, one string per line, markers included."""
    return [
        START,
        "## whatsnext",
        "",
        "`whatsnext` below is `python3 <plugin>/skills/whatsnext/scripts/whatsnext.py`.",
        "",
        "- At the start of a session read the resume note (`whatsnext progress resume-note`), or the active task's progress file in `%s/`." % progress_rel,
        "- Keep the progress file current: `whatsnext progress next \"<text>\"` sets the next action; `whatsnext progress stamp` records the state.",
        "- The plan is `%s`. When an item is done, prove it: `whatsnext plan done <id> --verify \"<cmd>\"`." % plan_rel,
        END,
    ]


class InitError(Exception):
    pass


def read_raw(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def find_block(text):
    """(start, end) offsets of the marked block in `text`, or None. Raises when the markers are broken."""
    start = text.find(START)
    if start < 0:
        if END in text:
            raise InitError("%s has %s without %s. Fix the markers by hand; nothing was changed." % (AGENTS, END, START))
        return None
    end = text.find(END, start + len(START))
    if end < 0:
        raise InitError("%s has %s without %s after it. Fix the markers by hand; nothing was changed." % (AGENTS, START, END))
    return start, end + len(END)


def appended(text, lines):
    """`text` with the block appended: a blank line between, the file's own line ending."""
    eol = "\r\n" if "\r\n" in text else "\n"
    block = eol.join(lines) + eol
    if not text:
        return block
    if not text.endswith("\n"):
        text += eol
    return text + eol + block


def without_block(text, span):
    """`text` minus the block, its trailing line break and one of the two blank lines around it."""
    start, end = span
    before, after = text[:start], text[end:]
    for eol in ("\r\n", "\n"):
        if after.startswith(eol):
            after = after[len(eol):]
            break
    if not after.strip() or after.startswith(("\r\n", "\n")):  # a blank line on both sides: keep one
        for eol in ("\r\n", "\n"):
            if before.endswith(eol * 2):
                before = before[:-len(eol)]
                break
    return before + after


def hooks_note():
    path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir, os.pardir, "hooks", "hooks.json"))
    where = path if os.path.isfile(path) else "%s (not found next to this script)" % path
    return ["Hooks: not installed by init. Claude Code loads the plugin's hooks from %s." % where,
            "For Codex run: whatsnext install-hooks --dry-run"]


def check_formats(root, folder):
    """Refuse when a progress file is written by a newer whatsnext (decision 14)."""
    for task in gwstatus.load_tasks(root, folder):
        if task.format > gwstatus.FORMAT:
            raise InitError("%s is format %d; this whatsnext knows format %d. Update whatsnext. Nothing was changed."
                            % (task.rel, task.format, gwstatus.FORMAT))


IGNORE_REL = ".gitignore"
IGNORE_LINE = ".whatsnext/sessions/"  # per-session hook state (journal.py); never committed
IGNORE_COVERS = (".whatsnext/sessions/", ".whatsnext/sessions", "/.whatsnext/sessions/", "/.whatsnext/sessions",
                 ".whatsnext/", ".whatsnext", "/.whatsnext/", "/.whatsnext")


def ignores_sessions(text):
    return any(line.strip() in IGNORE_COVERS for line in (text or "").splitlines())


def with_ignore_line(text):
    text = text or ""
    if text and not text.endswith("\n"):
        text += "\r\n" if "\r\n" in text else "\n"
    return text + IGNORE_LINE + ("\r\n" if "\r\n" in text else "\n")


def plan_init(root, effective):
    """Work out every step without writing. Returns a list of dicts: kind, rel, path, done (already there)."""
    plan_rel = effective.get("paths.plan")
    progress_rel = effective.get("paths.progress")
    folder = os.path.join(root, progress_rel)
    check_formats(root, folder)
    agents_path = os.path.join(root, AGENTS)
    steps = [
        {"kind": "file", "rel": plan_rel, "path": os.path.join(root, plan_rel), "text": PLAN_TEMPLATE},
        {"kind": "file", "rel": CONFIG_REL.replace(os.sep, "/"), "path": os.path.join(root, CONFIG_REL), "text": CONFIG_TEXT},
        {"kind": "dir", "rel": progress_rel.rstrip("/") + "/", "path": folder},
        {"kind": "dir", "rel": progress_rel.rstrip("/") + "/journal/", "path": os.path.join(folder, "journal")},
    ]
    for step in steps:
        step["done"] = os.path.exists(step["path"])
    ignore_path = os.path.join(root, IGNORE_REL)
    ignore_text = read_raw(ignore_path) if os.path.exists(ignore_path) else None
    steps.append({"kind": "ignore", "rel": IGNORE_REL, "path": ignore_path, "existing": ignore_text,
                  "done": ignores_sessions(ignore_text)})
    lines = block_lines(plan_rel, progress_rel.rstrip("/"))
    existing = None
    if os.path.exists(agents_path):
        existing = read_raw(agents_path)
    present = existing is not None and find_block(existing) is not None
    steps.append({"kind": "block", "rel": AGENTS, "path": agents_path, "lines": lines, "existing": existing,
                  "done": present})
    return steps


def describe(step, dry):
    will = "would " if dry else ""
    if step["kind"] == "block":
        if step["done"]:
            return "kept %s: the whatsnext block is already there" % step["rel"]
        if step["existing"] is None:
            return "%screate %s with the whatsnext block" % (will, step["rel"])
        return "%sappend the whatsnext block to %s (existing text is kept)" % (will, step["rel"])
    if step["kind"] == "ignore":
        if step["done"]:
            return "kept %s: it already ignores %s" % (step["rel"], IGNORE_LINE)
        return "%sadd %s to %s" % (will, IGNORE_LINE, step["rel"])
    if step["done"]:
        return "kept %s: it already exists" % step["rel"]
    return "%screate %s" % (will, step["rel"])


def apply_step(step):
    if step["done"]:
        return
    if step["kind"] == "dir":
        os.makedirs(step["path"], exist_ok=True)
    elif step["kind"] == "file":
        os.makedirs(os.path.dirname(step["path"]), exist_ok=True)
        with open(step["path"], "x", encoding="utf-8", newline="") as f:  # "x": never overwrite
            f.write(step["text"])
    elif step["kind"] == "ignore":
        write_raw(step["path"], with_ignore_line(step["existing"]))
    else:
        write_raw(step["path"], appended(step["existing"] or "", step["lines"]))


def do_init(root, effective, dry):
    steps = plan_init(root, effective)
    print("whatsnext init%s in %s" % (" (dry run)" if dry else "", root))
    for step in steps:
        print(describe(step, dry))
    if not dry:
        for step in steps:
            apply_step(step)
    for line in hooks_note():
        print(line)
    if dry:
        print("Dry run: nothing written.")
    elif all(step["done"] for step in steps):
        print("Nothing to change: whatsnext is already set up.")
    else:
        print("Done. Undo the AGENTS.md block with: whatsnext init --undo")
    return 0


def do_undo(root, effective, dry):
    path = os.path.join(root, AGENTS)
    print("whatsnext init --undo%s in %s" % (" (dry run)" if dry else "", root))
    text = read_raw(path) if os.path.exists(path) else None
    span = find_block(text) if text is not None else None
    if span is None:
        print("Nothing to remove: %s has no whatsnext block." % AGENTS)
    else:
        result = without_block(text, span)
        print("%sremove the whatsnext block from %s%s" % ("would " if dry else "", AGENTS, "" if result.strip() else " (the file is then empty, so it is deleted)"))
        if not dry:
            if result.strip():
                write_raw(path, result)
            else:
                os.remove(path)  # the block was the whole file: leave no empty AGENTS.md behind
    print("Left in place: %s, %s, %s/ with its journal folder, the %s line in %s, and the rest of %s."
          % (effective.get("paths.plan"), CONFIG_REL.replace(os.sep, "/"), effective.get("paths.progress").rstrip("/"),
             IGNORE_LINE, IGNORE_REL, AGENTS))
    if dry:
        print("Dry run: nothing written.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="whatsnext init", description="Adopt whatsnext in this git repository. Creates only what is missing; never overwrites.")
    parser.add_argument("--dry-run", action="store_true", help="print what would be created or appended; write nothing")
    parser.add_argument("--undo", action="store_true", help="remove the marked block from AGENTS.md; leave every other file")
    return parser


def run(argv, cwd=None):
    args = build_parser().parse_args(argv)
    root = gwconfig.find_root(cwd)
    if not gwstatus.in_git(root):
        print("whatsnext init needs a git repository, and %s is not inside one. Run `git init` first (folder mode is not built yet)." % root,
              file=sys.stderr)
        return 1
    effective = gwconfig.load(root)
    for message in effective.errors:
        print(message, file=sys.stderr)
    try:
        if args.undo:
            return do_undo(root, effective, args.dry_run)
        return do_init(root, effective, args.dry_run)
    except InitError as e:
        print(str(e), file=sys.stderr)
        return 1
