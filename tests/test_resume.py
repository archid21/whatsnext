"""Tests for `progress resume <id>` (P-57): the resume note for one task, from its newest handoff.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import StatusBase  # noqa: E402

from wn import config as wnconfig  # noqa: E402
from wn import wrapup as wnwrapup  # noqa: E402

HANDOFF = "docs/project/HANDOFF.md"
ARCHIVE = "docs/project/handoffs"


def note(task, written, next_action):
    return ("# Handoff\nSession: s1\nTask: %s\nWritten: %s\n\n## Goal\nShip it.\n\n## Next action\n%s\n"
            % (task, written, next_action))


class LatestHandoffTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()

    def latest(self, task_id="P-13"):
        found = wnwrapup.latest_handoff(self.proj, wnconfig.load(self.proj), task_id)
        return os.path.relpath(found[0], self.proj).replace(os.sep, "/") if found else None

    def test_newest_archived_note_for_the_task(self):
        self.put(ARCHIVE + "/20261101T0100Z-P-13.md", note("P-13", "2026-11-01T01:00Z", "old"))
        self.put(ARCHIVE + "/20261103T0100Z-P-13.md", note("P-13", "2026-11-03T01:00Z", "new"))
        self.put(ARCHIVE + "/20261105T0100Z-P-14.md", note("P-14", "2026-11-05T01:00Z", "other task"))
        self.put(HANDOFF, note("P-14", "2026-11-06T01:00Z", "other task"))
        self.assertEqual(self.latest(), ARCHIVE + "/20261103T0100Z-P-13.md")

    def test_handoff_note_wins_when_newer_or_equal(self):
        self.put(ARCHIVE + "/20261103T0100Z-P-13.md", note("P-13", "2026-11-03T01:00Z", "archived"))
        self.put(HANDOFF, note("P-13", "2026-11-03T01:00Z", "current"))
        self.assertEqual(self.latest(), HANDOFF)

    def test_none_when_no_note_is_for_the_task(self):
        self.put(HANDOFF, note("none", "2026-11-03T01:00Z", "x"))
        self.assertIsNone(self.latest())

    def test_files_the_archive_did_not_write_are_ignored(self):
        self.put(ARCHIVE + "/notes.md", note("P-13", "2026-11-09T01:00Z", "not an archive file"))
        self.assertIsNone(self.latest())

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_links_are_never_read(self):
        self.put("elsewhere.md", note("P-13", "2026-11-09T01:00Z", "linked"))
        os.makedirs(self.p(ARCHIVE), exist_ok=True)
        os.symlink(self.p("elsewhere.md"), self.p(ARCHIVE + "/20261109T0100Z-P-13.md"))
        self.assertIsNone(self.latest())


class ResumeCommandTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task("P-13", next_action="Run the login tests.")
        self.commit("task")

    def resume(self, task_id="P-13"):
        return self.gw(["progress", "resume", task_id])

    def test_prints_the_note_with_the_newest_handoff(self):
        self.put(ARCHIVE + "/20261101T0100Z-P-13.md", note("P-13", "2026-11-01T01:00Z", "Old step."))
        self.put(ARCHIVE + "/20261103T0100Z-P-13.md", note("P-13", "2026-11-03T01:00Z", "Write the form."))
        self.commit("notes")
        r = self.resume()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("continue P-13 Add login"), r.stdout)
        self.assertIn("Handoff: %s/20261103T0100Z-P-13.md, wrapped up 2026-11-03T01:00Z (read it first)" % ARCHIVE,
                      r.stdout)
        self.assertIn("Write the form.", r.stdout)
        self.assertNotIn("Old step.", r.stdout)
        self.assertIn("2 new commits", r.stdout)  # the task and notes commits, since the recorded one

    def test_another_tasks_handoff_note_is_not_used(self):
        self.put(HANDOFF, note("P-14", "2026-11-03T01:00Z", "Other work."))
        r = self.resume()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Handoff: none, facts only.", r.stdout)
        self.assertNotIn("Other work.", r.stdout)
        self.assertIn("Next: Run the login tests.", r.stdout)

    def test_works_for_a_task_that_is_not_active(self):
        self.task("P-20", title="Audit log", branch="p-20-audit", state="paused", next_action="Add the table.")
        self.git("branch", "p-20-audit")
        r = self.resume("P-20")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("continue P-20 Audit log (branch p-20-audit"), r.stdout)
        self.assertIn("Next: Add the table.", r.stdout)
        self.assertIn("Branch: you are on %s; P-20 is on p-20-audit. Run: git switch p-20-audit" % self.branch(),
                      r.stdout)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), self.branch())  # nothing switched

    def test_a_branch_that_is_gone_is_said_so(self):
        self.task("P-20", title="Audit log", branch="p-20-gone", state="paused")
        r = self.resume("P-20")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-20 is on p-20-gone. That branch no longer exists here.", r.stdout)
        self.assertNotIn("git switch", r.stdout)

    def test_same_branch_has_no_branch_line(self):
        r = self.resume()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Branch: you are on", r.stdout)

    def test_unknown_id_exits_1(self):
        r = self.resume("P-99")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no progress file for P-99", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_bad_id_exits_1(self):
        r = self.resume("../x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("task id", r.stderr)

    def test_claims_nothing_and_writes_nothing(self):
        before = self.get("docs/project/progress/P-13.md")
        self.resume()
        self.assertEqual(self.get("docs/project/progress/P-13.md"), before)
        self.assertEqual(self.git("status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
