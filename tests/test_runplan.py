"""Tests for the "Run the plan" option at the Start OK (P-46): an instruction to the agent, so the tests check the
instruction and the guide, and that the command the run ends with does what the instruction says.

Run: python3 -m unittest discover -s tests
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PlanBase  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class InstructionTests(unittest.TestCase):
    def setUp(self):
        text = read("skills", "whatsnext", "SKILL.md")
        start = text.index("3. After Start,")
        self.skill = text[start:text.index("\n## ", start)]
        self.guide = read("docs", "GUIDE.md")

    def test_offers_three_answers_with_run_all_first_and_recommended(self):
        answers = re.findall(r"- \*\*([^*]+)\*\*", self.skill)
        self.assertEqual(answers, ["Run all steps, then verify and mark done.", "Go step by step.", "Change the steps."])
        self.assertIn("(the first is recommended)", self.skill)

    def test_run_all_states_each_rule(self):
        for words in ("approves once", "in order without asking again", "plan done <id> --verify", "last 20 lines",
                      "do not mark the item done", "do not retry in a loop", "ask the user for evidence",
                      "permission the user has not given", "Never skip the verify step"):
            self.assertIn(words, self.skill)

    def test_guide_says_the_same(self):
        for words in ("Run all steps, then verify and mark done", "(recommended)", "approve once", "last 20 lines",
                      "leaves the item open", "never skips the verify step"):
            self.assertIn(words, self.guide)


class VerifyEndsTheRunTests(PlanBase):
    """What the last step does: a passing command confirms the item, a failing one leaves it open with its output."""

    def test_a_passing_command_marks_it_confirmed(self):
        r = self.plan("done", "P-14", "--override-reason", "Approved test command", "--verify", "true")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Marked P-14 done. Verified", r.stdout)

    def test_a_failing_command_leaves_it_open_and_shows_the_output(self):
        r = self.plan("done", "P-14", "--override-reason", "Approved test command", "--verify", "for i in $(seq 1 30); do echo line$i; done; exit 3")
        self.assertNotEqual(r.returncode, 0)
        out = r.stdout + r.stderr
        self.assertIn("line30", out)
        self.assertNotIn("line5\n", out)  # only the last 20 lines
        r = self.plan("list")
        self.assertRegex(r.stdout, r"P-14.*\[open\]|P-14.*open")


if __name__ == "__main__":
    unittest.main()
