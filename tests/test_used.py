"""Tests for the handoff's Files, Links and Skills sections (P-68): from the session's tool calls, no model call.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import HookBase, entry, write_jsonl  # noqa: E402

from wn import used as wnused  # noqa: E402

T1 = "2026-11-10T20:00:00.000Z"
T2 = "2026-11-10T21:00:00.000Z"


def tool(when, name, sidechain=False, **data):
    item = entry("assistant", when, [{"type": "tool_use", "id": "t", "name": name, "input": data}])
    if sidechain:
        item["isSidechain"] = True
    return item


class UsedBase(HookBase):
    def transcript(self, items):
        path = os.path.join(self.tmp.name, "t.jsonl")
        write_jsonl(path, [entry("user", T1, "hi", cwd=self.proj)] + items)
        return path

    def sample(self, when=T2):
        p = self.p
        return [
            tool(when, "Read", file_path=p("src/app.py")),
            tool(when, "Read", file_path=p("src/app.py")),  # a duplicate
            tool(when, "Read", file_path=p("src/form.py")),
            tool(when, "Edit", file_path=p("src/form.py")),  # read, then changed: not a Read entry
            tool(when, "Write", file_path=p("src/new.py")),  # written first: created
            tool(when, "Read", file_path="/etc/hosts"),  # outside the repository
            tool(when, "Read", file_path=os.path.join(os.path.expanduser("~"), ".claude", "CLAUDE.md")),
            tool(when, "WebFetch", url="https://docs.example.com/guide?token=abc123#part", prompt="x"),
            tool(when, "mcp__Claude_Browser__navigate", url="http://localhost:3000/login"),
            tool(when, "mcp__Claude_Browser__navigate", url="javascript:alert(1)"),
            tool(when, "Skill", skill="commit-commands:commit"),
            tool(when, "Read", sidechain=True, file_path=p("src/agent.py")),  # a subagent's read
        ]


class CollectTests(UsedBase):
    def test_lists(self):
        facts = wnused.collect(self.transcript(self.sample()), self.proj)
        self.assertEqual(facts["read"], ["src/app.py"])
        self.assertEqual(facts["created"], ["src/new.py"])
        self.assertEqual(facts["links"], ["https://docs.example.com/guide", "http://localhost:3000/login"])
        self.assertEqual(facts["skills"], ["commit-commands:commit"])

    def test_since_leaves_out_older_entries(self):
        path = self.transcript([tool(T1, "Read", file_path=self.p("old.py")), tool(T2, "Read", file_path=self.p("new.py"))])
        since = wnused.gwsessions.parse_time("2026-11-10T20:30:00Z")
        self.assertEqual(wnused.collect(path, self.proj, since)["read"], ["new.py"])

    def test_codex_skill_from_its_skill_file(self):
        item = {"type": "response_item", "timestamp": T2,
                "payload": {"type": "function_call", "name": "shell",
                            "arguments": '{"command": ["cat", "skills/whatsnext/SKILL.md"]}'}}
        self.assertEqual(wnused.collect(self.transcript([item]), self.proj)["skills"], ["whatsnext"])

    def test_values_are_cleaned(self):
        path = self.transcript([tool(T2, "Skill", skill="x\x1b[31m api_key=" + "s" * 30)])
        skill = wnused.collect(path, self.proj)["skills"][0]
        self.assertNotIn("\x1b", skill)
        self.assertNotIn("s" * 30, skill)


class NoteTests(unittest.TestCase):
    FACTS = {"read": ["a.py", "b.py"], "created": ["c.py"], "links": ["https://x.test/"], "skills": ["s"]}

    def test_sections_text(self):
        self.assertEqual(wnused.sections_text(self.FACTS),
                         "## Files\n\n- Read: a.py, b.py\n- Created: c.py\n\n## Links\n\n- https://x.test/\n\n## Skills\n\ns")

    def test_empty_lists_add_nothing(self):
        body = "# Handoff\n\n## Goal\n\nx\n"
        self.assertEqual(wnused.add_to_note(body, {"read": [], "created": [], "links": [], "skills": []}, 3000), body)

    def test_long_lists_are_cut(self):
        facts = {"read": ["f%d.py" % i for i in range(15)], "created": [], "links": [], "skills": []}
        self.assertIn("f9.py, and 5 more", wnused.sections_text(facts))

    def test_the_note_stays_within_the_limit_and_the_agents_text_is_kept(self):
        body = "# Handoff\n\n## Goal\n\n" + "g" * 2900 + "\n"
        facts = {"read": ["file_%03d.py" % i for i in range(10)], "created": [], "links": [], "skills": []}
        text = wnused.add_to_note(body, facts, 3000)
        self.assertLessEqual(len(text), 3000)
        self.assertTrue(text.startswith(body.rstrip()))
        self.assertIn("more", text)
        tight = wnused.add_to_note(body + "h" * 95, facts, 3000)
        self.assertNotIn("## Files", tight)  # nothing fits: the note is unchanged

    def test_old_sections_are_replaced(self):
        body = "# Handoff\n\n## Files\n\n- Read: old.py\n\n## Goal\n\nx\n\n## Skills\n\nold\n"
        text = wnused.add_to_note(body, self.FACTS, 3000)
        self.assertNotIn("old", text)
        self.assertEqual(text.count("## Files"), 1)
        self.assertIn("## Goal\n\nx", text)


class WrapUpTests(UsedBase):
    NOTE = "# Handoff\nSession: s1\nTask: P-13\nWritten: 2026-11-10T21:30Z\n\n## Goal\n\nShip it.\n"

    def test_stop_adds_the_sections_and_skips_the_note_itself(self):
        path = self.transcript(self.sample() + [tool(T2, "Write", file_path=self.p("docs/project/HANDOFF.md"))])
        self.prompt("wrap up")
        self.put("docs/project/HANDOFF.md", self.NOTE)
        self.hook("stop", {"session_id": "s1", "cwd": self.proj, "transcript_path": path})
        note = self.get("docs/project/HANDOFF.md")
        self.assertIn("## Files\n\n- Read: src/app.py\n- Created: src/new.py\n", note)
        self.assertIn("## Links\n\n- https://docs.example.com/guide\n- http://localhost:3000/login\n", note)
        self.assertIn("## Skills\n\ncommit-commands:commit\n", note)
        self.assertNotIn("HANDOFF.md", note.split("## Files")[1])
        self.assertNotIn("token", note)
        self.assertEqual(len(self.wrapups()), 1)  # still recorded

    def test_only_tool_calls_since_this_sessions_last_wrap_up(self):
        self.put("docs/project/HANDOFF.md", self.NOTE.replace("21:30Z", "20:30Z"))  # this session's earlier note
        path = self.transcript([tool(T1, "Read", file_path=self.p("before.py")), tool(T2, "Read", file_path=self.p("after.py"))])
        self.prompt("wrap up")  # archives the earlier note
        self.put("docs/project/HANDOFF.md", self.NOTE)
        self.hook("stop", {"session_id": "s1", "cwd": self.proj, "transcript_path": path})
        note = self.get("docs/project/HANDOFF.md")
        self.assertIn("- Read: after.py\n", note)
        self.assertNotIn("before.py", note)

    def test_no_transcript_leaves_the_note_as_written(self):
        self.prompt("wrap up")
        self.put("docs/project/HANDOFF.md", self.NOTE)
        self.hook("stop", {"session_id": "s1", "cwd": self.proj, "transcript_path": os.path.join(self.tmp.name, "none")})
        self.assertEqual(self.get("docs/project/HANDOFF.md"), self.NOTE)
        self.assertEqual(len(self.wrapups()), 1)

    def test_the_instructions_say_not_to_write_them(self):
        self.assertIn("Do not write `## Files`, `## Links` or `## Skills` sections", self.prompt("wrap up"))


if __name__ == "__main__":
    unittest.main()
