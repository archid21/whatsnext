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


class WrapupStatusTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def test_wrapup_status_no_handoff_says_facts_only(self):
        out = self.hook("session-start", {"source": "startup", "session_id": "s1"})
        self.assertIn("Handoff: none, facts only.", out)
        self.assertLessEqual(len(out), 1200)

    def test_wrapup_status_a_handoff_says_when_it_was_wrapped_up(self):
        path = os.path.join(self.proj, "docs", "project", "HANDOFF.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(note(session="s1", written="2026-11-05T05:03Z"))
        out = self.hook("session-start", {"source": "startup", "session_id": "s1"})
        self.assertIn("Handoff: docs/project/HANDOFF.md, wrapped up 2026-11-05T05:03Z (read it first)", out)
        self.assertNotIn("facts only", out)
        self.assertLessEqual(len(out), 1200)

    def test_wrapup_status_is_dropped_before_the_cap_cuts_next(self):
        self.task(next_action="n" * 380, title="t" * 200)
        out = self.hook("session-start", {"source": "startup", "session_id": "s1"})
        self.assertLessEqual(len(out), 1200)
        self.assertIn("Next:", out)


class CutLineTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()

    def note(self):
        return self.hook("session-start", {"source": "startup", "session_id": "s1"})

    def test_cut_line_a_note_that_fits_has_none(self):
        self.task(done="- Wrote the form\n- Added the tests")
        self.commit("task")
        out = self.note()
        self.assertNotIn("cut:", out)

    def test_cut_line_names_what_the_cap_left_out(self):
        done = "\n".join("- Finished step %d of the long job: %s" % (i, "w" * 90) for i in range(8))
        self.task(done=done, title="t" * 90, next_action="n" * 380)
        self.commit("task")
        for i in range(6):
            self.put("src/f%d.py" % i, "x\n")
            self.commit("feat: change number %d with a long subject line %s" % (i, "s" * 50))
        out = self.note()
        self.assertLessEqual(len(out), 1200)
        last = out.rstrip("\n").splitlines()[-1]
        self.assertRegex(last, r"^cut: (Done \+\d+)?(, )?(\d+ commits?)?\. Full: progress show$")
        self.assertIn("Done +", last)
        self.assertIn("Next:", out)  # Next is never the loss

    def test_cut_line_counts_are_right(self):
        from wn import packet as wnpacket
        task = type("T", (), {"section": lambda self, name: "\n".join("- e%d" % i for i in range(7)) if name == "Done" else ""})()
        facts = {"new": 9, "commits": [("a", "x")] * 9, "dirty": [], "problem": None}
        state = {"done": 2, "commits": 1}
        self.assertEqual(wnpacket.cut_line(task, facts, state), "cut: Done +6, 8 commits. Full: progress show")
        self.assertIsNone(wnpacket.cut_line(task, facts, {"done": 0, "commits": 3}))
        self.assertEqual(wnpacket.cut_line(task, facts, {"done": 0, "commits": 0}), "cut: 9 commits. Full: progress show")


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
