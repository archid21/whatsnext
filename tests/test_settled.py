"""Tests for the settled list (P-93, ADR-0036): docs/project/SETTLED.md copied from the handoff, shown in the resume note.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import HookBase  # noqa: E402

from wn import settled as wnsettled  # noqa: E402
from wn import transcript as wntranscript  # noqa: E402
from wn import wrapup as wnwrapup  # noqa: E402

SETTLED = "docs/project/SETTLED.md"
HANDOFF = "docs/project/HANDOFF.md"


class SettledBase(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def note(self, settled):
        section = "" if settled is None else "\n## Settled\n%s\n" % settled
        self.put(HANDOFF, "# Handoff\n\nSession: s1\nTask: P-13\nWritten: 2026-11-06T10:00Z\n\n## Goal\nx\n\n"
                          "## Next action\nGo.\n%s" % section)

    def wrap_up(self, settled, session="s1"):
        self.prompt("wrap up", session=session)
        self.note(settled)
        self.stop(session=session)

    def settled_lines(self):
        return [l for l in self.get(SETTLED).split("\n") if l.startswith("- ")] if self.has(SETTLED) else []


class CopyTests(SettledBase):
    def test_appends_new_lines_with_a_header(self):
        self.wrap_up("- dropped: chose B over A, do not revisit A (docs/decisions/ADR-0007-init.md)\n"
                     "- use: python3 -m unittest (docs/project/handoffs/x.md)\n"
                     "- expected: the security hook runs first (docs/decisions/ADR-0005-hooks-and-journal.md)")
        self.assertEqual(self.settled_lines(), [
            "- dropped: chose B over A, do not revisit A (docs/decisions/ADR-0007-init.md)",
            "- use: python3 -m unittest (docs/project/handoffs/x.md)",
            "- expected: the security hook runs first (docs/decisions/ADR-0005-hooks-and-journal.md)"])
        self.assertTrue(self.get(SETTLED).startswith("# Settled"))

    def test_second_wrap_up_with_the_same_lines_adds_none(self):
        lines = "- dropped: chose B over A (docs/decisions/ADR-0007-init.md)"
        self.wrap_up(lines)
        self.wrap_up(lines.upper().replace("DOCS/DECISIONS/ADR-0007-INIT.MD", "docs/decisions/ADR-0007-init.md"), session="s1")
        self.wrap_up("- dropped:   chose  b over A   (docs/decisions/ADR-0001-scope.md)\n- use: tool X (docs/decisions/ADR-0002-plan-and-progress-files.md)")
        self.assertEqual(len(self.settled_lines()), 2)
        self.assertEqual(self.settled_lines()[0], "- dropped: chose B over A (docs/decisions/ADR-0007-init.md)")

    def test_none_and_malformed_lines_are_skipped(self):
        self.wrap_up("none")
        self.assertFalse(self.has(SETTLED))
        self.wrap_up("- maybe: not a kind (docs/x.md)\n- dropped:\n- use: none\nplain words\n- use no colon\n"
                     "- use: keep this one (docs/decisions/ADR-0001-scope.md)")
        self.assertEqual(self.settled_lines(), ["- use: keep this one (docs/decisions/ADR-0001-scope.md)"])

    def test_missing_source_gets_the_handoff_path(self):
        self.wrap_up("- dropped: chose B over A\n- expected: a note (not a path) shows up")
        self.assertEqual(self.settled_lines(), [
            "- dropped: chose B over A (%s)" % HANDOFF,
            "- expected: a note (not a path) shows up (%s)" % HANDOFF])

    def test_secrets_are_masked(self):
        self.wrap_up("- use: set password=hunter2hunter2 in the env (docs/x.md)")
        self.assertNotIn("hunter2", self.get(SETTLED))

    def test_old_note_without_the_section_adds_nothing(self):
        self.wrap_up(None)
        self.assertFalse(self.has(SETTLED))
        self.assertEqual(len(self.wrapups()), 1)

    def test_hooks_json_is_unchanged_in_shape(self):
        # no new hook entry: the copy runs inside the existing Stop step
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hooks.json")) as f:
            self.assertNotIn("settled", f.read().lower())


class InstructionTests(SettledBase):
    def test_wrap_up_instructions_ask_for_a_settled_section(self):
        out = self.prompt("wrap up")
        self.assertIn("these nine `##` sections", out)
        self.assertIn("9. `## Settled`", out)
        self.assertIn("At most %d characters" % wnwrapup.MAX_SETTLED_CHARS, out)

    def test_transcript_prompt_asks_for_it_and_the_check_accepts_it(self):
        self.assertIn("9. `## Settled`", wntranscript.prompt())
        good = ("## Goal\ng\n\n## Next action\ndo\nVerify: `true`\nIf it fails: look\n\n## State\nState on x.\nCheck: clean\n\n"
                "## What changed\nnone\n\n## Decisions\nnone\n\n## Constraints\nnone\n\n"
                "## Open questions and blockers\nnone\n\n## Dead ends\nnone\n")
        self.assertEqual(wntranscript.problems(good), [])
        self.assertEqual(wntranscript.problems(good + "\n## Settled\n- use: x (docs/a.md)\n"), [])
        self.assertTrue(wntranscript.problems(good + "\n## Settled\n" + "x" * 401))
        self.assertTrue(wntranscript.problems(good.replace("## Dead ends", "## Settled\nnone\n\n## Dead ends")))


class ResumeNoteTests(SettledBase):
    def add(self, n):
        lines = ["- dropped: choice number %d (docs/decisions/ADR-0001-scope.md)" % i for i in range(1, n + 1)]
        self.put(SETTLED, wnsettled.HEADER + "\n".join(lines) + "\n")

    def test_no_file_shows_nothing(self):
        self.assertNotIn("Settled", self.packet()["text"])

    def test_empty_file_shows_nothing(self):
        self.put(SETTLED, wnsettled.HEADER)
        self.assertNotIn("Settled", self.packet()["text"])

    def test_shows_lines_newest_first(self):
        self.add(3)
        text = self.packet()["text"]
        self.assertIn("Settled (docs/project/SETTLED.md", text)
        self.assertLess(text.index("choice number 3"), text.index("choice number 2"))
        self.assertLess(text.index("choice number 2"), text.index("choice number 1"))
        self.assertNotIn("more in", text)

    def test_caps_at_five_lines_and_points_to_the_file(self):
        self.add(8)
        text = self.packet()["text"]
        shown = [l for l in text.split("\n") if l.startswith("- dropped: choice")]
        self.assertEqual(len(shown), 5)
        self.assertIn("choice number 8", text)
        self.assertNotIn("choice number 3 ", text)
        self.assertIn("(3 more in docs/project/SETTLED.md)", text)
        self.assertLessEqual(len(text), 1200)

    def test_long_lines_are_clipped(self):
        self.put(SETTLED, wnsettled.HEADER + "- use: " + "w " * 200 + "(docs/a.md)\n")
        line = [l for l in self.packet()["text"].split("\n") if l.startswith("- use:")][0]
        self.assertLessEqual(len(line), 2 + 110)

    def test_no_task_note_shows_it_too(self):
        os.remove(self.p("docs/project/progress/P-13.md"))
        self.add(2)
        text = self.packet()["text"]
        self.assertIn("No active task", text)
        self.assertIn("choice number 2", text)


if __name__ == "__main__":
    unittest.main()
