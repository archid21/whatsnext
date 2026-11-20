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
        self.assertEqual(sorted(data), ["claims", "current", "errors", "handoff", "message", "open",
                                      "ready", "recommended", "warnings"])

    def test_open_lists_every_open_item_and_claims_lists_claimed_ones(self):  # ADR-0033
        self.task("P-14", next_action="Add the 429 test.")
        self.set_claim("P-14", agent="codex", updated=ts(1), branch=self.branch())
        data = self.status()
        ids = [v["id"] for v in data["open"]]
        self.assertIn("P-13", ids)
        self.assertIn("P-14", ids)
        self.assertTrue(all(v["status"] != "done" for v in data["open"]))
        self.assertEqual([c["id"] for c in data["claims"]], ["P-14"])
        self.assertEqual(data["claims"][0]["agent"], "codex")
        self.assertEqual(data["claims"][0]["branch"], self.branch())

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

    def set_plan_status(self, task_id, status):
        path = self.p("%s/%s.md" % (STATUS, task_id))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        text = text.replace("- **Decisions:** none\n", "- **Decisions:** none\n- **Plan:** docs/project/plans/%s-2026-11-16.md (%s)\n" % (task_id, status))
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_shown_plan_is_reported_and_needs_approval_after_takeover(self):
        """P-82: a plan another agent only showed is not approved by a takeover; status says so."""
        self.task("P-14", next_action="Add the 429 test.")
        self.set_claim("P-14", agent="codex", updated=ts(1), branch=self.branch())
        self.assertIsNone(self.status()["current"]["plan_status"])
        self.set_plan_status("P-14", "shown")
        self.assertEqual(self.status()["current"]["plan_status"], "shown")
        text = self.gw(["status"]).stdout
        self.assertIn("Plan shown, not approved: ask before running its steps. A takeover yes is not plan approval.", text)
        self.assertIn("A takeover yes is not plan approval.", self.gw(["progress", "resume-note"]).stdout)
        self.set_plan_status("P-14", "approved")
        self.assertEqual(self.status()["current"]["plan_status"], "approved")
        self.assertNotIn("not plan approval", self.gw(["status"]).stdout)

    def test_skill_says_a_takeover_is_not_plan_approval(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "skills", "whatsnext", "SKILL.md"),
                  encoding="utf-8") as f:
            skill = f.read()
        self.assertIn("A yes to a takeover or to resuming is not plan approval.", skill)
        self.assertIn("Taking it over does not approve its plan", skill)

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
