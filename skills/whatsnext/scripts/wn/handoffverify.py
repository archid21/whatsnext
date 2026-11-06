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
from . import plan as gwplan
from . import status as gwstatus
from . import wrapup as gwwrapup

VERIFY_LINE_RE = re.compile(r"^\s*verify\s*:\s*(.+?)\s*$", re.IGNORECASE)


def verify_command(body):
    """The command on the `Verify:` line of the note's Next action section, or None."""
    lines = body.split("\n")
    section = gwstatus.get_section(lines, "Next action")
    for line in section.split("\n"):
        m = VERIFY_LINE_RE.match(line)
        if m:
            command = m.group(1).strip()
            if len(command) >= 2 and command[0] == command[-1] == "`":
                command = command[1:-1].strip()
            return command or None
    return None


def is_tracked(root, path):
    """True when git tracks `path` (so a clone of the repository carries it)."""
    return gwstatus.git(root, "ls-files", "--error-unmatch", "--", path)[0] == 0


def archived_copy(root, effective):
    """The archive file whose content equals the note's, or None."""
    handoff = gwwrapup.handoff_path(root, effective)
    folder = os.path.join(os.path.dirname(handoff), gwwrapup.ARCHIVE_DIR)
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
    command = verify_command(body)
    if not command:
        print("%s has no `Verify:` line under `## Next action`. Nothing was run." % rel, file=sys.stderr)
        return 1
    if is_tracked(root, handoff) and not args.allow_tracked:
        print("%s is tracked by git, so a clone of this repository carries it and its command is not yours. "
              "Nothing was run.\nRead the command: %s\nIf you trust it, run: whatsnext handoff verify --allow-tracked"
              % (rel, command), file=sys.stderr)
        return 2
    ctx = gwplan.Ctx(root, effective)
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
