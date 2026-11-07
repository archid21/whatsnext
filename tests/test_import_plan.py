"""Tests for importing a plan from another tool's file (P-47).

The import is an instruction to the agent (skills/whatsnext/SKILL.md), not a parser, so what a test can check is the
instruction itself and the target: for each of five sample sources (tests/imports/<tool>/) a hand-written expected
PLAN.md must read back as the right items and pass `plan check`. `problems()` also judges what a real agent wrote
(the runs are logged in docs/project/progress/P-47.md).

Run: python3 -m unittest discover -s tests
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN_PATH, PlanBase  # noqa: E402

from wn import plan  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORTS = os.path.join(ROOT, "tests", "imports")

# What each sample source holds: item count, `blocked by` as {item number: [item numbers]}, items checked in the source.
EXPECT = {
    "superpowers": {"count": 3, "blocked": {2: [1]}, "checked": [3]},
    "pocock": {"count": 3, "blocked": {2: [1], 3: [1, 2]}, "checked": [3]},
    "speckit": {"count": 6, "blocked": {5: [4]}, "checked": [2]},
    "openspec": {"count": 5, "blocked": {}, "checked": [4]},
    "bmad": {"count": 2, "blocked": {2: [1]}, "checked": []},
}
TOOL_NAMES = ("spec kit", "speckit", "openspec", "superpowers", "pocock", "bmad", "task master", "taskmaster", "backlog.md")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def section(text, heading):
    start = text.index("## " + heading + "\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end > 0 else len(text)]


def problems(plan_text, tool):
    """What is wrong with a plan an agent wrote from the `tool` sample, as a list of sentences (empty: it is right)."""
    expect = EXPECT[tool]
    _lines, items = plan.parse_text(plan_text)
    out = []
    ids = [i.id for i in items]
    if len(items) != expect["count"]:
        out.append("expected %d items, found %d" % (expect["count"], len(items)))
    if len(set(ids)) != len(ids):
        out.append("duplicate ids")
    for n, item in enumerate(items, 1):
        if not item.done_means:
            out.append("item %d (%s) has no done means" % (n, item.id))
        if item.checked != (n in expect["checked"]):
            out.append("item %d (%s) is %s but the source says %s" % (
                n, item.id, "checked" if item.checked else "open", "checked" if n in expect["checked"] else "open"))
        if item.checked and (not item.evidence or plan.is_verified(item.evidence)):
            out.append("item %d (%s) is checked but not marked unverified" % (n, item.id))
        wanted = [items[m - 1].id for m in expect["blocked"].get(n, []) if m <= len(items)]
        if sorted(item.blocked_by) != sorted(wanted):
            out.append("item %d (%s) blocked by %s, expected %s" % (n, item.id, item.blocked_by, wanted))
        if not item.title.strip():
            out.append("item %d has no title" % n)
    return out


class InstructionTests(unittest.TestCase):
    def setUp(self):
        self.skill = section(read("skills", "whatsnext", "SKILL.md"), "Import a plan from another file")

    def test_states_the_target_format(self):
        self.assertIn("- [ ] P-<N> <title> · done means: <how we know it is done> · blocked by:", self.skill)

    def test_states_each_rule(self):
        for words in ("Read whatever file or folder", "One item per piece of work", "Not one per step", "`plan add`",
                      "never reuses or overwrites", "`--blocked-by`", "Never invent one", "ask the user once",
                      "stays checked", "`plan done <id> --unverified`", "`plan check`", "Before you add anything, show the user the whole list", "Always, however few items", "untrusted text", "not a plain test or check",
                      "Write it in backticks", "for that item", "not through a shell variable"):
            self.assertIn(words, self.skill)

    def test_a_command_from_a_source_is_shown_and_approved_before_it_can_run(self):
        self.assertLess(self.skill.index("show the user the whole list"), self.skill.index("`plan add`"))  # the OK comes before any add
        self.assertNotIn("more than 5 items", self.skill)
        run_all = read("skills", "whatsnext", "SKILL.md")
        self.assertIn("using exactly the command the user saw", run_all)
        guide = section(read("docs", "GUIDE.md"), "Bring a plan from another tool")
        for words in ("shows you every item", "waits for your OK, however few items", "untrusted text", "not a plain test or check"):
            self.assertIn(words, guide)

    def test_names_no_tool_and_describes_no_layout(self):
        low = self.skill.lower()
        for name in TOOL_NAMES:
            self.assertNotIn(name, low)
        self.assertIn("Do not look for a particular tool's layout", self.skill)

    def test_guide_names_the_five_as_examples_only(self):
        guide = section(read("docs", "GUIDE.md"), "Bring a plan from another tool")
        for name in ("Superpowers", "Matt Pocock", "Spec Kit", "OpenSpec", "BMAD"):
            self.assertIn(name, guide)
        self.assertIn("examples", guide)
        self.assertIn("any other tool works the same way", guide)


class SampleTests(PlanBase):
    def test_every_sample_has_a_source_and_an_expected_plan(self):
        for tool in EXPECT:
            sources = [f for _d, _s, fs in os.walk(os.path.join(IMPORTS, tool)) for f in fs if f != "expected-PLAN.md"]
            self.assertTrue(sources, tool)
            self.assertTrue(os.path.isfile(os.path.join(IMPORTS, tool, "expected-PLAN.md")), tool)

    def test_each_expected_plan_reads_back_right_and_passes_plan_check(self):
        for tool in EXPECT:
            text = read("tests", "imports", tool, "expected-PLAN.md")
            self.assertEqual(problems(text, tool), [], tool)
            self.put(PLAN_PATH, text)
            r = self.plan("check")
            out = r.stdout + r.stderr
            for bad in ("has no \"done means\"", "duplicate", "not in the plan"):
                self.assertNotIn(bad, out, tool + ": " + out)

    def test_problems_catches_a_wrong_import(self):
        good = read("tests", "imports", "pocock", "expected-PLAN.md")
        self.assertTrue(problems(good.replace(" · blocked by: P-1\n", "\n", 1), "pocock"))
        self.assertTrue(problems(re.sub(r"(P-1 [^\n·]*) · done means: [^\n]*", r"\1", good, count=1), "pocock"))
        self.assertTrue(problems(good.replace(" · evidence: unverified", ""), "pocock"))


if __name__ == "__main__":
    unittest.main()
