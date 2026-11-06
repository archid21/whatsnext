"""Tests for the "Dead ends" section of the handoff note and the compact text (P-24).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_handoff import note  # noqa: E402
from test_wrapup import HookBase  # noqa: E402

from wn import wrapup as wnwrapup  # noqa: E402

DEAD = "Tried sqlite: locks under two agents. Tried a flat file: no atomic claim."


def with_dead_ends(text=DEAD):
    return note().rstrip("\n") + "\n\n## Dead ends\n" + text + "\n"


class DeadEndsTests(unittest.TestCase):
    def test_dead_ends_the_line_template_has_a_slot(self):
        self.assertIn("Dead ends: <dead ends, at most 300 characters>", wnwrapup.line_template())

    def test_dead_ends_the_compact_line_carries_them_within_300_characters(self):
        line = wnwrapup.compact_line(with_dead_ends())
        self.assertIn("Dead ends: " + DEAD, line)
        long_line = wnwrapup.compact_line(with_dead_ends("x" * 900))
        self.assertIn("x" * 299 + "…", long_line)
        self.assertNotIn("x" * 301, long_line)
        self.assertNotIn("\n", long_line)
        self.assertLessEqual(len(long_line), wnwrapup.MAX_LINE_CHARS)

    def test_dead_ends_none_is_left_out_and_they_are_cut_first(self):
        self.assertNotIn("Dead ends:", wnwrapup.compact_line(with_dead_ends("none")))
        body = with_dead_ends("d" * 300).replace("Ship the forms.", "g" * 500)
        body = body.replace("none\n\n## Constraints", "q" * 400 + "\n\n## Constraints")
        line = wnwrapup.compact_line(body.replace("Do not touch auth.", "c" * 600).replace("Run the form tests.", "n" * 290))
        self.assertLessEqual(len(line), wnwrapup.MAX_LINE_CHARS)
        self.assertIn("n" * 290, line)
        self.assertIn("c" * 600, line)

    def test_dead_ends_the_text_no_longer_says_to_drop_them_without_an_exception(self):
        for base in (wnwrapup.LINE_BASE, wnwrapup.COMPACT_BASE):
            self.assertNotIn("and dead ends.", base)
            self.assertIn("dead ends", base)
            self.assertIn("keep", base.lower().split("drop:")[1])

    def test_dead_ends_the_body_keeps_the_section_when_it_fits(self):
        fitted = wnwrapup.fit_body(with_dead_ends(), 1500, "docs/project/HANDOFF.md")
        self.assertIn("## Dead ends\n" + DEAD, fitted)
        tight = wnwrapup.fit_body(with_dead_ends() + "\n## Extra\n" + "z" * 5000, 700, "docs/project/HANDOFF.md")
        self.assertIn("Run the form tests.", tight)  # Next action stays whatever is cut


class DeadEndsPromptTests(HookBase):
    def test_dead_ends_the_wrap_up_prompt_asks_for_the_section(self):
        self.cfg()
        self.task()
        self.commit("task")
        out = self.prompt("wrap up")
        self.assertIn("these eight `##` sections", out)
        self.assertIn("8. `## Dead ends`", out)
        self.assertIn("with the reason", out)
        self.assertIn("Dead ends: <dead ends, at most 300 characters>", out)


if __name__ == "__main__":
    unittest.main()
