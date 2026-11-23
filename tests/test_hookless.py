"""Tests for the instructions tier: an agent with no hooks (ADR-0027, P-75).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import ROOT, RepoBase  # noqa: E402

from wn import initcmd  # noqa: E402

SKILL = ROOT / "skills" / "whatsnext" / "SKILL.md"
SECTIONS = ("## Goal", "## Next action", "## State", "## What changed", "## Decisions",
            "## Constraints", "## Open questions and blockers", "## Dead ends", "## Settled")


class RulesTests(unittest.TestCase):
    """The AGENTS.md block and SKILL.md each state both hook-free rules."""

    def test_block_says_run_status_at_start(self):
        text = "\n".join(initcmd.block_lines("docs/project/PLAN.md", "docs/project/progress"))
        self.assertIn("start of every session run `wn status`", text)

    def test_block_says_wrap_up_without_a_hook(self):
        text = "\n".join(initcmd.block_lines("docs/project/PLAN.md", "docs/project/progress"))
        self.assertIn("`wrap up` and no whatsnext hook answered, run `wn wrap-up-instructions`", text)

    def test_skill_states_both_rules(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("At the start of every session, run `status`", text)
        self.assertIn("no whatsnext hook added instructions, run `wrap-up-instructions`", text)


class CommandTests(RepoBase):
    def test_prints_the_handoff_sections_and_a_hook_free_ending(self):
        r = self.gw(["wrap-up-instructions", "--project", self.proj])
        self.assertEqual(r.returncode, 0, r.stderr)
        for section in SECTIONS:
            self.assertIn(section, r.stdout)
        self.assertIn("Handoff written: ", r.stdout)
        self.assertIn('say "what\'s next?"', r.stdout)

    def test_never_promises_what_only_a_hook_does(self):
        out = self.gw(["wrap-up-instructions", "--project", self.proj]).stdout
        self.assertNotIn("whatsnext adds them", out)
        self.assertNotIn("whatsnext copies it", out)
        self.assertNotIn("Choose above the prompt", out)

    def test_a_missing_folder_is_refused(self):
        r = self.gw(["wrap-up-instructions", "--project", os.path.join(self.proj, "nope")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a folder", r.stderr)


if __name__ == "__main__":
    unittest.main()
