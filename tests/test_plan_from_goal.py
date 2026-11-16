"""P-72: SKILL.md has a plan-from-a-goal flow, and the AGENTS.md block says to ask before adding work.

Run: python3 -m unittest discover -s tests
"""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import SCRIPT  # noqa: E402,F401  (puts the scripts folder on sys.path)

from wn import initcmd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "whatsnext" / "SKILL.md"


def section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end > 0 else len(text)]


class PlanFromGoalTests(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        self.flow = section(self.text, "## Plan from a goal")

    def test_command_table_routes_to_the_flow(self):
        self.assertIn('| "plan this: <goal>"', self.text)

    def test_asks_before_adding(self):
        self.assertIn('ask once: "Turn this into plan items?" Add nothing without a yes.', self.flow)

    def test_every_item_gets_a_done_means_and_none_is_invented(self):
        self.assertIn("Each item gets a done means", self.flow)
        self.assertIn("Never invent one.", self.flow)

    def test_shows_the_list_and_placement_before_adding(self):
        self.assertIn("Show the whole list", self.flow)
        self.assertIn("**Next (default)**, Now or Later", self.flow)
        self.assertIn("existing items are never moved or reordered", self.flow)
        self.assertIn("Wait for the OK.", self.flow)

    def test_reuses_overlapping_items(self):
        self.assertIn("reuse it as a `blocked by` instead of adding a duplicate", self.flow)

    def test_writes_only_through_plan_add(self):
        self.assertIn("`plan add", self.flow)
        self.assertIn("Never edit PLAN.md by hand.", self.flow)
        self.assertIn("`plan check`", self.flow)

    def test_agents_block_says_ask_then_plan_add(self):
        block = "\n".join(initcmd.block_lines("docs/project/PLAN.md", "docs/project/progress"))
        self.assertIn("To add work to the plan, ask the user first, then use `wn plan add`", block)



class ItemOverviewTests(unittest.TestCase):
    """P-83: offered items come with an overview."""

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_skill_has_the_overview_section(self):
        sec = section(self.text, "## Item overview")
        for part in ("**What it is:**", "**How it will work:**", "**Impact and importance:**", "Do not invent facts"):
            self.assertIn(part, sec)

    def test_whats_next_and_start_flow_use_it(self):
        self.assertIn("the `ready` items, each with an item overview", self.text)
        self.assertIn("give each offered item an item overview, then ask one pop-up", self.text)

    def test_agents_block_states_it(self):
        block = "\n".join(initcmd.block_lines("docs/project/PLAN.md", "docs/project/progress"))
        self.assertIn("give each a short overview first: what it is, how it will work, its impact and importance", block)


if __name__ == "__main__":
    unittest.main()
