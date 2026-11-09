"""Tests for `whatsnext status` (P-55): one call for the current item, handoff, ready items and warnings.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN, PLAN_PATH, STATUS, PlanBase, StatusBase, minute_ts, ts  # noqa: E402

from wn import overview as wnoverview  # noqa: E402

HANDOFF = "docs/project/HANDOFF.md"


def note(session="s1", task="none", written=None, branch=None, next_action="Run the form tests.", questions="none"):
    head = "# Handoff\nSession: %s\nTask: %s\nWritten: %s\n" % (session, task, written or minute_ts(30))
    if branch:
        head += "Branch: %s\n" % branch
    return head + "\n## Goal\nShip it.\n\n## Next action\n%s\n\n## Open questions and blockers\n%s\n" % (
        next_action, questions)


class StatusTests(PlanBase):
    def status(self, *args, **kw):
        r = self.gw(["status", "--json"] + list(args), **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_fields_are_always_there(self):
        data = self.status()
        self.assertEqual(sorted(data), ["current", "errors", "handoff", "message", "ready", "recommended", "warnings"])

    def test_no_current_item_lists_ready_items_and_recommends_the_first(self):
        data = self.status()
        self.assertIsNone(data["current"])
        self.assertEqual([v["id"] for v in data["ready"]], ["P-13", "P-14"])  # Next only fills in when Now is empty
        self.assertEqual(data["recommended"], "P-13")
        self.assertIsNone(data["handoff"])

    def test_current_item_comes_first_and_is_not_repeated_in_ready(self):
        self.task("P-14", next_action="Add the 429 test.")
        self.set_claim("P-14", agent="codex", updated=ts(1), branch=self.branch())
        data = self.status()
        self.assertEqual(data["current"]["id"], "P-14")
        self.assertEqual(data["current"]["next_action"], "Add the 429 test.")
        self.assertEqual(data["recommended"], "P-14")
        self.assertNotIn("P-14", [v["id"] for v in data["ready"]])

    def test_limit(self):
        self.assertEqual(len(self.status("--limit", "1")["ready"]), 1)

    def test_handoff_from_this_session_says_read_it_first(self):
        self.put(HANDOFF, note(session="s1"))
        data = self.status("--session", "s1")
        self.assertEqual(data["handoff"]["path"], HANDOFF)
        self.assertTrue(data["handoff"]["read_first"])
        self.assertEqual(data["handoff"]["label"], "read it first")
        self.assertEqual(data["handoff"]["next_action"], "Run the form tests.")

    def test_handoff_from_another_session_is_labelled(self):
        self.put(HANDOFF, note(session="s2"))
        data = self.status("--session", "s1")
        self.assertFalse(data["handoff"]["read_first"])
        self.assertEqual(data["handoff"]["label"], "another session's note")

    def test_session_comes_from_the_environment(self):
        self.put(HANDOFF, note(session="env-s"))
        self.env["WHATSNEXT_SESSION"] = "env-s"
        r = self.gw(["status", "--json"])
        self.assertTrue(json.loads(r.stdout)["handoff"]["read_first"])

    def test_plan_check_warnings_are_included(self):
        self.put(PLAN_PATH, PLAN + "- [x] P-17 Unproven\n")
        self.assertTrue(any("P-17" in w for w in self.status()["warnings"]))

    def test_nothing_ready_gives_a_message(self):
        self.put(PLAN_PATH, "# Plan\n\n## Now\n- [x] P-1 Done · done means: x · evidence: by hand\n")
        data = self.status()
        self.assertEqual(data["ready"], [])
        self.assertIsNone(data["recommended"])
        self.assertTrue(data["message"])

    def test_text_form(self):
        self.put(HANDOFF, note(session="s2"))
        r = self.gw(["status", "--session", "s1"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Ready:", r.stdout)
        self.assertIn("P-13 Add login  [recommended]", r.stdout)
        self.assertIn("(another session's note)", r.stdout)


class NoPlanTests(StatusBase):
    def test_no_plan_no_handoff(self):
        self.cfg()
        r = self.gw(["status", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIsNone(data["current"])
        self.assertEqual(data["ready"], [])
        self.assertIsNone(data["handoff"])
        self.assertTrue(data["message"])
        self.assertIn("Handoff: none.", self.gw(["status"]).stdout)


class FoldDriftTests(unittest.TestCase):
    def test_drift_warnings_become_one_line(self):
        warnings = ["P-%d was verified at abc1234, and the code has changed since (3 commits). Run its verify again." % n
                    for n in range(1, 8)] + ["P-9 has no \"done means\"."]
        out = wnoverview.fold_drift(warnings)
        self.assertEqual(len(out), 2)
        self.assertIn("P-9", out[0])
        self.assertIn("7 done items", out[1])
        self.assertIn("P-1, P-2, P-3, P-4, P-5, ...", out[1])

    def test_no_drift_leaves_warnings_alone(self):
        self.assertEqual(wnoverview.fold_drift(["a"]), ["a"])


if __name__ == "__main__":
    unittest.main()
