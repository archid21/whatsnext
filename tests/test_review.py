"""Tests for `review: required` and `plan review <id>` (P-58, ADR-0022).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

REVIEW_PLAN = """# Plan

## Now
- [ ] P-13 Login page · done means: `test -f README.md` · review: required
- [ ] P-14 Rate-limit the API · done means: `test -f README.md`
## Next
- [ ] P-15 Password reset · done means: `false` · review: required
"""


class ReviewTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.put(PLAN_PATH, REVIEW_PLAN)
        self.commit("review plan")

    def line(self, item_id):
        return next(l for l in self.get(PLAN_PATH).split("\n") if " %s " % item_id in l)

    def status_of(self, item_id):
        _r, data = self.jplan("list")
        return next(v for v in data["items"] if v["id"] == item_id)

    def verify(self, item_id="P-13"):
        self.assertEqual(self.start(item_id, "--branch", "stay").returncode, 0)
        return self.plan("done", item_id, "--verify")

    def test_passing_check_waits_for_review(self):
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-13 is awaiting review", r.stdout)
        self.assertTrue(self.line("P-13").startswith("- [ ] P-13"), self.line("P-13"))
        self.assertIn("evidence: verified: test -f README.md passed", self.line("P-13"))
        self.assertFalse(self.has_claim("P-13"))
        self.assertEqual(self.status_of("P-13")["status"], "awaiting review")
        self.assertIn("[awaiting review]", self.plan("list").stdout)
        self.assertIn("**State:** review", self.get("docs/project/progress/P-13.md"))

    def test_awaiting_item_is_not_recommended(self):
        self.verify()
        _r, data = self.jplan("next")
        self.assertEqual([c["id"] for c in data["candidates"]], ["P-14"])
        self.assertEqual(data["recommended"]["id"] if isinstance(data["recommended"], dict) else data["recommended"],
                         "P-14")

    def test_review_ticks_the_item(self):
        self.verify()
        r = self.plan("review", "P-13")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Marked P-13 done. Reviewed", r.stdout)
        line = self.line("P-13")
        self.assertTrue(line.startswith("- [x] P-13"), line)
        self.assertRegex(line, r"evidence: verified: .* · reviewed: \d{4}-\d\d-\d\dT\d\d:\d\dZ$")
        view = self.status_of("P-13")
        self.assertEqual(view["status"], "done")
        self.assertTrue(view["verified"])
        self.assertIn("**State:** done", self.get("docs/project/progress/P-13.md"))

    def test_reject_sends_it_back_and_keeps_the_old_run(self):
        self.verify()
        r = self.plan("review", "P-13", "--reject", "Button is misaligned")
        self.assertEqual(r.returncode, 0, r.stderr)
        line = self.line("P-13")
        self.assertTrue(line.startswith("- [ ] P-13"), line)
        self.assertIn("evidence: rejected: Button is misaligned (", line)
        self.assertIn("evidence: verified: test -f README.md passed", line)  # the old run stays
        self.assertEqual(self.status_of("P-13")["status"], "open")
        self.assertNotEqual(self.plan("review", "P-13").returncode, 0)  # needs a fresh --verify first
        self.assertEqual(self.verify().returncode, 0)
        self.assertEqual(self.status_of("P-13")["status"], "awaiting review")

    def test_reject_needs_a_reason(self):
        self.verify()
        r = self.plan("review", "P-13", "--reject", "  ")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--reject needs the person's reason", r.stderr)

    def test_review_refused_before_the_check_passes(self):
        r = self.plan("review", "P-13")
        self.assertEqual(r.returncode, 1)
        self.assertIn("P-13 is not awaiting review: it is open", r.stderr)

    def test_review_refused_for_items_without_the_field(self):
        r = self.plan("review", "P-14")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no `review: required` field", r.stderr)

    def test_failed_check_changes_nothing(self):
        before = self.line("P-15")
        r = self.verify("P-15")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.line("P-15"), before)
        self.assertEqual(self.status_of("P-15")["status"], "in progress")

    def test_evidence_and_unverified_are_refused(self):
        for flags in (["--evidence", "looked fine"], ["--unverified"]):
            r = self.plan("done", "P-13", *flags)
            self.assertEqual(r.returncode, 1, flags)
            self.assertIn("needs a person's review (ADR-0022)", r.stderr)
        self.assertTrue(self.line("P-13").startswith("- [ ] P-13"))

    def test_items_without_the_field_work_as_before(self):
        r = self.verify("P-14")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.line("P-14").startswith("- [x] P-14"))
        self.assertEqual(self.status_of("P-14")["status"], "done")

    def test_review_field_is_in_the_json_view(self):
        self.assertTrue(self.status_of("P-13")["review"])
        self.assertFalse(self.status_of("P-14")["review"])


if __name__ == "__main__":
    unittest.main()
