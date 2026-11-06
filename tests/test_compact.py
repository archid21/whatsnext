"""Tests for the facts-only compact text (P-5): the keep-list built from the progress file and git
when there is no fresh handoff note.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import StatusBase  # noqa: E402

from wn import compact as wncompact  # noqa: E402
from wn import config as wnconfig  # noqa: E402
from wn import hook as wnhook  # noqa: E402

STEPS = ["- [x] Write the form", "- [ ] Add the tests", "- [ ] Ship it"]


class FactsOnlyTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task(steps=STEPS)
        self.commit("task")
        self.put("src/login.py", "x\n")
        self.put("README.md", "changed\n")

    def facts(self):
        effective = wnconfig.load(self.proj)
        return wncompact.facts_text(self.proj, effective, wnhook.branch_task(self.proj, effective)), effective

    def test_facts_only(self):
        text, effective = self.facts()
        self.assertNotIn("\n", text)
        self.assertLessEqual(len(text), wncompact.MAX_FACTS_CHARS)
        self.assertIn("P-13", text)
        self.assertIn("branch " + self.branch(), text)
        self.assertIn("Next: Run the login tests.", text)
        self.assertIn("Plan step 2 of 3: Add the tests.", text)
        self.assertIn("Files changed: README.md, src/login.py.", text)
        task = wnhook.branch_task(self.proj, effective)
        line = wncompact.facts_line(self.proj, effective, task)
        self.assertNotIn("\n", line)
        self.assertTrue(line.endswith(text))

    def test_facts_only_json_and_precompact_use_the_same_text(self):
        text, _effective = self.facts()
        r = self.gw(["compact-instructions", "--json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertIsNone(data["compact_line"])  # no handoff note: ADR-0009 item 2 is unchanged
        self.assertTrue(data["facts_line"].endswith(text))
        out = self.gw(["hook", "pre-compact", "--agent", "claude-code"], stdin=json.dumps({"session_id": "s1"})).stdout
        self.assertIn(text, out)

    def test_facts_only_long_file_list_is_cut_and_no_task_gives_none(self):
        for i in range(12):
            self.put("src/f%02d.py" % i, "x\n")
        text, _effective = self.facts()
        self.assertIn("+6 more", text)  # 14 files, 8 shown
        self.assertNotIn("\n", text)
        self.tmp_none = self.gw(["compact-instructions", "--json", "--project", self.tmp.name])
        self.assertIsNone(json.loads(self.tmp_none.stdout)["facts_line"])


class SubagentsTests(StatusBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def use(self, name, tool_input, tool_id):
        return {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}]}}

    def result(self, tool_id):
        return {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "content": "done"}]}}

    def precompact(self, entries):
        path = os.path.join(self.tmp.name, "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        r = self.gw(["hook", "pre-compact", "--agent", "claude-code"],
                    stdin=json.dumps({"session_id": "s1", "transcript_path": path}))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def test_subagents(self):
        out = self.precompact([
            self.use("Agent", {"description": "Research competitors", "subagent_type": "general-purpose"}, "a1"),
            self.use("Agent", {"description": "Review the diff", "subagent_type": "code-reviewer"}, "a2"),
            self.result("a2"),
            self.use("TodoWrite", {"todos": [{"content": "Write tests", "status": "completed"},
                                             {"content": "Fix the parser", "status": "in_progress"}]}, "t1"),
        ])
        self.assertIn("Research competitors (general-purpose, running)", out)
        self.assertIn("Review the diff (code-reviewer, finished)", out)
        self.assertIn("In-progress todo: Fix the parser.", out)
        self.assertNotIn("Write tests", out)
        self.assertLessEqual(len(out), 3000)

    def test_subagents_task_tools_and_nothing_open(self):
        out = self.precompact([
            self.use("TaskCreate", {"subject": "First job"}, "c1"),
            self.use("TaskCreate", {"subject": "Second job"}, "c2"),
            self.use("TaskUpdate", {"taskId": "2", "status": "in_progress"}, "u1"),
        ])
        self.assertIn("In-progress todo: Second job.", out)
        self.assertNotIn("First job", out)
        quiet = self.precompact([{"type": "user", "message": {"role": "user", "content": "hello"}}])
        self.assertNotIn("Subagents launched", quiet)
        self.assertNotIn("In-progress todo", quiet)


if __name__ == "__main__":
    unittest.main()
