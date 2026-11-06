"""Tests for `whatsnext handoff verify` (P-23).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import StatusBase  # noqa: E402

HANDOFF = "docs/project/HANDOFF.md"


def note(verify="test -f README.md"):
    return ("# Handoff\n\nSession: s0\nTask: P-13\nWritten: 2026-11-05T05:03Z\n\n## Goal\nx\n\n## Next action\nRun it.\n"
            "Verify: `%s`\n\n## State\nok\n" % verify)


class HandoffVerifyTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.put("README.md", "hi\n")

    def verify(self, *args):
        return self.gw(["handoff", "verify"] + list(args))

    def archived(self):
        folder = self.p("docs/project/handoffs")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_handoff_verify_exit_0_archives_the_note(self):
        self.put(HANDOFF, note())
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Verify passed", r.stdout)
        self.assertEqual(self.archived(), ["20261105T0503Z-P-13.md"])
        self.assertFalse(self.has(HANDOFF))

    def test_handoff_verify_a_failing_command_keeps_the_note(self):
        self.put(HANDOFF, note("test -f missing-file.txt"))
        r = self.verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("Verify failed", r.stderr)
        self.assertTrue(self.has(HANDOFF))
        self.assertEqual(self.archived(), [])

    def test_handoff_verify_a_git_tracked_note_refuses_without_the_flag(self):
        self.put(HANDOFF, note("touch RAN.txt"))
        self.commit("track the note")
        r = self.verify()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("tracked by git", r.stderr)
        self.assertIn("touch RAN.txt", r.stderr)  # the person can read what it would run
        self.assertFalse(self.has("RAN.txt"))
        self.assertTrue(self.has(HANDOFF))
        r = self.verify("--allow-tracked")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has("RAN.txt"))
        self.assertFalse(self.has(HANDOFF))

    def test_handoff_verify_no_note_no_line_or_bad_argument(self):
        self.assertEqual(self.verify().returncode, 1)
        self.put(HANDOFF, "# Handoff\n\n## Next action\nGo.\n")
        r = self.verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no `Verify:` line", r.stderr)
        self.assertEqual(self.gw(["handoff", "bogus"]).returncode, 2)


if __name__ == "__main__":
    unittest.main()
