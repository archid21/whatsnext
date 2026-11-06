"""`whatsnext handoff verify` (P-23): run the handoff note's `Verify:` line, and archive the note when it passes.

The person starts it; no hook runs it. A note that git tracks came from the repository, so anyone who can push
could have written its command: it is not run unless the person passes `--allow-tracked`.
"""

import argparse
import hashlib
import os
import re
import sys

from . import config as gwconfig
from . import packet as gwpacket
from . import plan as gwplan
from . import status as gwstatus
from . import wrapup as gwwrapup

VERIFY_LINE_RE = re.compile(r"^verify\s*:\s*(.+?)\s*$", re.IGNORECASE)  # at the start of a line: no indent
SHOW_MAX = 300


def shown(command):
    """The command for a person to read: control characters removed, long text clipped."""
    return gwpacket.clip(gwpacket.clean(command), SHOW_MAX)


def verify_commands(body):
    """Every `Verify:` line in the note's Next action section, outside code fences and not indented."""
    section = gwstatus.get_section(body.split("\n"), "Next action")
    found, fenced = [], False
    for line in section.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        m = None if fenced else VERIFY_LINE_RE.match(line)
        if m:
            command = m.group(1).strip()
            if len(command) >= 2 and command[0] == command[-1] == "`":
                command = command[1:-1].strip()
            if command:
                found.append(command)
    return found


def verify_command(body):
    """The note's one `Verify:` command, or None (none, or more than one: see `verify_commands`)."""
    found = verify_commands(body)
    return found[0] if len(found) == 1 else None


def is_tracked(root, path):
    """True unless git says plainly that `path` is not tracked. Outside git, or when git cannot answer, the note's
    provenance is unknown, so it counts as tracked (the person must pass --allow-tracked)."""
    if not gwstatus.in_git(root):
        return True
    return gwstatus.git(root, "ls-files", "--error-unmatch", "--", path)[0] != 1


def archived_copy(root, effective):
    """The archive file whose content equals the note's, or None."""
    handoff = gwwrapup.handoff_path(root, effective)
    folder = os.path.join(os.path.dirname(handoff), gwwrapup.ARCHIVE_DIR)
    inside = os.path.realpath(root)
    if os.path.islink(folder) or os.path.commonpath([os.path.realpath(os.path.dirname(folder)), inside]) != inside:
        return None  # the same guards the archive keeps: no link may lead out of the project
    try:
        with open(handoff, "rb") as f:
            want = hashlib.sha256(f.read().decode("utf-8", "replace").encode("utf-8", "replace")).hexdigest()
        names = os.listdir(folder)
    except OSError:
        return None
    for name in sorted(names):
        path = os.path.join(folder, name)
        if gwwrapup.ARCHIVE_NAME_RE.match(name) and not os.path.islink(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    if hashlib.sha256(f.read().encode("utf-8", "replace")).hexdigest() == want:
                        return path
            except OSError:
                continue
    return None


def run(argv):
    parser = argparse.ArgumentParser(prog="whatsnext handoff verify",
                                     description="Run the handoff note's `Verify:` line; on exit 0, archive the note.")
    parser.add_argument("action", choices=["verify"])
    parser.add_argument("--allow-tracked", action="store_true",
                        help="run the command even though git tracks the note (the repository wrote it)")
    args = parser.parse_args(argv)
    root = gwconfig.find_root()
    effective = gwconfig.load(root)
    handoff = gwwrapup.handoff_path(root, effective)
    rel = gwconfig.display_path(handoff, root)
    try:
        with open(handoff, encoding="utf-8", errors="replace") as f:
            body = f.read()
    except OSError:
        print("No handoff note at %s." % rel, file=sys.stderr)
        return 1
    found = verify_commands(body)
    if len(found) != 1:
        print("%s has %s under `## Next action`. Nothing was run." % (
            rel, "no `Verify:` line" if not found else "%d `Verify:` lines (it needs exactly one)" % len(found)), file=sys.stderr)
        return 1
    command = found[0]
    if is_tracked(root, handoff) and not args.allow_tracked:
        print("%s is tracked by git (or git cannot say), so its command may not be yours. "
              "Nothing was run.\nRead the command: %s\nIf you trust it, run: whatsnext handoff verify --allow-tracked"
              % (rel, shown(command)), file=sys.stderr)
        return 2
    ctx = gwplan.Ctx(root, effective)
    print("Running: %s" % shown(command), flush=True)
    result = gwplan.run_verify(root, command, gwplan.verify_timeout(ctx))
    took = gwplan.format_seconds(result["seconds"])
    if not result["passed"]:
        print("Verify failed (%s): %s. The note stays in place." % (
            gwplan.failure_reason(result, gwplan.verify_timeout(ctx)), gwplan.short_command(command)), file=sys.stderr)
        for line in gwplan.output_tail(result["output"]):
            print("    " + line, file=sys.stderr)
        return 1
    try:
        gwwrapup.archive_handoff(root, effective)
    except Exception as e:  # without a saved copy the note is never removed
        print("Verify passed in %s, but the note could not be archived (%s). It stays in place." % (took, e), file=sys.stderr)
        return 1
    saved = archived_copy(root, effective)
    if saved is None:
        print("Verify passed in %s, but no archived copy of %s was found. It stays in place." % (took, rel), file=sys.stderr)
        return 1
    os.remove(handoff)
    print("Verify passed in %s: %s\nArchived %s to %s and removed the note." % (
        took, gwplan.short_command(command), rel, gwconfig.display_path(saved, root)))
    return 0
