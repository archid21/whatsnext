"""Tests for `plan edit` and `plan reopen` (P-59): the id and history stay.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

PLAN = """# Plan

## Now
- [ ] P-13 Add login · done means: `test -f README.md` · blocked by: P-14 · suggest: sonnet/high
- [x] P-14 Rate-limit the API · done means: `true` · evidence: verified: true passed in 0 s (2026-11-01T10:00Z) at abc1234 t:deadbeef · reviewed: 2026-11-01T11:00Z
- [ ] P-15 Reset · done means: `true` · review: required · evidence: verified: true passed in 0 s (2026-11-02T10:00Z)
- [ ] P-16 Audit <!-- later --> · done means: `true`
"""
PROGRESS = "docs/project/progress/%s.md"


class EditReopenBase(PlanBase):
    def setUp(self):
        super().setUp()
        self.put(PLAN_PATH, PLAN)
        self.commit("plan")

    def line(self, item_id):
        return next(l for l in self.get(PLAN_PATH).split("\n") if l.startswith(("- [ ] %s " % item_id, "- [x] %s " % item_id)))

    def history(self, item_id):
        text = self.get(PROGRESS % item_id)
        return text.split("## History", 1)[1] if "## History" in text else ""

    def view(self, item_id):
        _r, data = self.jplan("list")
        return next(v for v in data["items"] if v["id"] == item_id)


class EditTests(EditReopenBase):
    def test_title_changes_and_other_fields_stay(self):
        r = self.plan("edit", "P-13", "--title", "Add sign-in")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.line("P-13"), "- [ ] P-13 Add sign-in · done means: `test -f README.md` · blocked by: P-14 "
                                             "· suggest: sonnet/high")
        self.assertRegex(self.history("P-13"), r"- \d{4}-\d\d-\d\dT\d\d:\d\dZ edited title: Add login -> Add sign-in")

    def test_done_means_changes(self):
        r = self.plan("edit", "P-13", "--done-means", "`python3 -m unittest`")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("· done means: `python3 -m unittest` · blocked by: P-14", self.line("P-13"))
        self.assertIn("edited done means: `test -f README.md` -> `python3 -m unittest`", self.history("P-13"))
        self.assertEqual(self.view("P-13")["done_means"], "`python3 -m unittest`")

    def test_new_check_clears_a_run_awaiting_review(self):
        self.assertEqual(self.view("P-15")["status"], "awaiting review")
        r = self.plan("edit", "P-15", "--done-means", "`false`")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("evidence:", self.line("P-15"))
        self.assertIn("review: required", self.line("P-15"))
        self.assertIn("cleared for the new check: evidence: verified: true passed", self.history("P-15"))
        self.assertEqual(self.view("P-15")["status"], "open")

    def test_done_means_of_a_done_item_is_refused(self):
        before = self.get(PLAN_PATH)
        r = self.plan("edit", "P-14", "--done-means", "`false`")
        self.assertEqual(r.returncode, 1)
        self.assertIn("plan reopen P-14", r.stderr)
        self.assertEqual(self.get(PLAN_PATH), before)

    def test_title_of_a_done_item_can_change(self):
        r = self.plan("edit", "P-14", "--title", "Rate-limit")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.line("P-14").startswith("- [x] P-14 Rate-limit · done means: `true` · evidence: verified:"))
        self.assertEqual(self.view("P-14")["status"], "done")

    def test_needs_something_to_change(self):
        r = self.plan("edit", "P-13")
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs --title, --done-means or both", r.stderr)

    def test_empty_title_is_refused(self):
        r = self.plan("edit", "P-13", "--title", "  ")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--title must not be empty", r.stderr)

    def test_same_text_is_unchanged(self):
        r = self.plan("edit", "P-13", "--title", "Add login")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-13 is unchanged", r.stdout)
        self.assertFalse(self.has(PROGRESS % "P-13"))

    def test_unknown_item(self):
        r = self.plan("edit", "P-99", "--title", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No item P-99", r.stderr)

    def test_line_with_a_comment_is_left_to_a_person(self):
        r = self.plan("edit", "P-16", "--title", "Audit log")
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTML comment", r.stderr)

    def test_new_progress_file_is_parked_not_active(self):
        self.plan("edit", "P-13", "--title", "Add sign-in")
        self.assertIn("**State:** parked", self.get(PROGRESS % "P-13"))
        r = self.gw(["progress", "show"])
        self.assertIn("No active task.", r.stdout)

    def test_existing_progress_file_keeps_its_state(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.plan("edit", "P-13", "--title", "Add sign-in")
        text = self.get(PROGRESS % "P-13")
        self.assertIn("**State:** active", text)
        self.assertIn("edited title: Add login -> Add sign-in", text)


class ReopenTests(EditReopenBase):
    def test_reopen_moves_the_evidence_to_history(self):
        r = self.plan("reopen", "P-14", "--reason", "429 not sent on bursts")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.line("P-14"), "- [ ] P-14 Rate-limit the API · done means: `true`")
        history = self.history("P-14")
        self.assertIn("reopened: 429 not sent on bursts; was: evidence: verified: true passed in 0 s "
                      "(2026-11-01T10:00Z) at abc1234 t:deadbeef; reviewed: 2026-11-01T11:00Z", history)
        self.assertEqual(self.view("P-14")["status"], "open")
        self.assertIn("**State:** parked", self.get(PROGRESS % "P-14"))

    def test_reopen_with_a_new_check(self):
        r = self.plan("reopen", "P-14", "--reason", "needs a real test", "--done-means", "`test -f README.md`")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.line("P-14"), "- [ ] P-14 Rate-limit the API · done means: `test -f README.md`")
        self.assertIn("edited done means: `true` -> `test -f README.md`", self.history("P-14"))

    def test_reopened_item_needs_a_fresh_check(self):
        self.plan("reopen", "P-14", "--reason", "again")
        self.assertEqual(self.start("P-14", "--branch", "stay").returncode, 0)
        r = self.plan("done", "P-14", "--verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.line("P-14").startswith("- [x] P-14"))
        self.assertIn("reopened: again", self.history("P-14"))  # the old run is still on record

    def test_reopen_unblocks_nothing(self):
        self.plan("reopen", "P-14", "--reason", "again")
        self.assertEqual(self.view("P-13")["blocked_on"], ["P-14"])

    def test_only_done_items_reopen(self):
        r = self.plan("reopen", "P-13", "--reason", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("P-13 is not done", r.stderr)

    def test_reason_is_required(self):
        r = self.plan("reopen", "P-14", "--reason", " ")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--reason must not be empty", r.stderr)
        self.assertTrue(self.line("P-14").startswith("- [x] P-14"))


if __name__ == "__main__":
    unittest.main()
