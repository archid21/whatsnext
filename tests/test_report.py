"""P-62: `plan report` prints one line per item from journal facts only.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

JOURNAL = """# Journal: P-13

- 2026-11-01T10:00Z stop abc1234 b dirty=0 files: a.py
- 2026-11-01T10:30Z pre-compact abc1234 b dirty=1
- 2026-11-01T11:00Z stop def5678 b dirty=0
- 2026-11-01T11:05Z verify def5678 b dirty=0
- 2026-11-01T12:15Z session-end def5678 b dirty=0
"""


class ReportTests(PlanBase):
    def journal(self, item_id, text):
        rel = "docs/project/progress/journal/%s.md" % item_id
        self.put(rel, text)

    def plan_text(self):
        with open(os.path.join(self.proj, PLAN_PATH), encoding="utf-8") as f:
            return f.read()

    def test_counts_from_the_journal(self):
        self.journal("P-13", JOURNAL)
        r, out = self.jplan("report")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = [x for x in out["items"] if x["id"] == "P-13"][0]
        self.assertEqual((row["turns"], row["sessions"], row["compacts"], row["commits"], row["failed_verifies"]),
                         (2, 1, 1, 2, 1))
        self.assertEqual(row["elapsed"], "2h 15m")
        self.assertEqual(row["verify_attempts"], 1)
        self.assertFalse(row["done"])

    def test_text_line_and_estimate_note(self):
        self.journal("P-13", JOURNAL)
        r = self.plan("report")
        self.assertIn("P-13 2h 15m, 2 turns, 1 sessions, 1 compacts, 2 commits, 1 verify attempt (1 failed)", r.stdout)
        self.assertIn("so it is an estimate", r.stdout)

    def test_a_verified_done_item_counts_the_passing_run(self):
        self.journal("P-13", JOURNAL)
        self.plan("edit", "P-13", "--done-means", "`true`")
        r = self.plan("done", "P-13", "--verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r, out = self.jplan("report", "P-13")
        row = out["items"][0]
        self.assertTrue(row["done"])
        self.assertEqual(row["verify_attempts"], 2)

    def test_named_item_without_journal_says_so(self):
        r = self.plan("report", "P-14")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-14 no journal", r.stdout)

    def test_no_journals_at_all(self):
        r = self.plan("report")
        self.assertIn("No item has a journal yet.", r.stdout)

    def test_unknown_id_fails(self):
        self.assertEqual(self.plan("report", "P-999").returncode, 1)

    def test_writes_nothing(self):
        self.journal("P-13", JOURNAL)
        before = self.plan_text()
        self.plan("report")
        self.assertEqual(self.plan_text(), before)

    def test_elapsed_formats(self):
        from wn import plan
        self.assertEqual(plan.elapsed_text("2026-11-01T10:00Z", "2026-11-01T10:42Z"), "42m")
        self.assertEqual(plan.elapsed_text("2026-11-01T10:00Z", "2026-11-04T13:00Z"), "3d 3h")
        self.assertEqual(plan.elapsed_text(None, None), "-")


if __name__ == "__main__":
    unittest.main()
