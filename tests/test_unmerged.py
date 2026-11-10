"""Tests for `plan check` flagging done items whose branch is not merged into main (P-60).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

PLAN = """# Plan

## Now
- [x] P-13 Add login · done means: `true` · evidence: checked (2026-11-01T10:00Z)
- [ ] P-14 Rate-limit the API · done means: `true`
"""


class UnmergedTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.git("branch", "-M", "main")
        self.put(PLAN_PATH, PLAN)
        self.commit("plan")

    def on_branch(self, branch, item_id="P-13", state="done"):
        """Make `branch` with one commit, and a progress file for `item_id` that names it."""
        self.git("switch", "-q", "-c", branch)
        self.put("src/%s.txt" % branch, "work\n")
        self.commit("work on " + branch)
        self.git("switch", "-q", "main")
        self.task(item_id, branch=branch, state=state)
        self.commit("progress")

    def warnings(self):
        r = self.plan("check", "--json")
        return [w for w in json.loads(r.stdout)["warnings"] if "not merged" in w]

    def test_unmerged_branch_warns(self):
        self.on_branch("p-13-add-login")
        self.assertEqual(self.warnings(), ["P-13 is done, not merged: branch p-13-add-login is not in main."])
        self.assertIn("warning: P-13 is done, not merged: branch p-13-add-login is not in main.",
                      self.plan("check").stdout)

    def test_merged_branch_is_quiet(self):
        self.on_branch("p-13-add-login")
        self.git("merge", "-q", "--no-edit", "p-13-add-login")
        self.assertEqual(self.warnings(), [])

    def test_cherry_picked_branch_counts_as_merged(self):
        self.on_branch("p-13-add-login")
        sha = self.git("rev-parse", "p-13-add-login")
        self.git("cherry-pick", sha)
        self.assertNotEqual(self.git("branch", "--no-merged", "main"), "")  # git alone says not merged
        self.assertEqual(self.warnings(), [])

    def test_deleted_branch_is_skipped(self):
        self.on_branch("p-13-add-login")
        self.git("branch", "-D", "p-13-add-login")
        self.assertEqual(self.warnings(), [])

    def test_item_on_main_is_skipped(self):
        self.task("P-13", branch="main", state="done")
        self.assertEqual(self.warnings(), [])

    def test_open_item_is_not_checked(self):
        self.on_branch("p-14-rate", item_id="P-14", state="active")
        self.assertEqual(self.warnings(), [])

    def test_no_progress_file_is_skipped(self):
        self.assertEqual(self.warnings(), [])

    def test_one_branch_for_two_items(self):
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-14", "- [x] P-14"))
        self.commit("P-14 done")
        self.on_branch("shared")
        self.task("P-14", branch="shared", state="done")
        self.assertEqual(self.warnings(), ["P-13 is done, not merged: branch shared is not in main.",
                                           "P-14 is done, not merged: branch shared is not in main."])

    def test_status_json_shows_it(self):
        self.on_branch("p-13-add-login")
        r = self.gw(["status", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("P-13 is done, not merged: branch p-13-add-login is not in main.", json.loads(r.stdout)["warnings"])


if __name__ == "__main__":
    unittest.main()
