"""P-91: journal lines and handoffs say which agent wrote them; old lines without the field still parse."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "whatsnext", "scripts"))
from wn import journal, packet, plan, wrapup  # noqa: E402


class AgentFieldTests(unittest.TestCase):
    def test_journal_line_carries_the_agent_after_the_state(self):
        line = journal.format_line("2026-11-18T20:00Z", "stop", "abc1234", "main", 2, ["a.py"], "1a2b3c", "codex")
        self.assertEqual(line, "- 2026-11-18T20:00Z stop abc1234 main dirty=2 set=1a2b3c agent=codex files: a.py")
        m = journal.STATE_RE.match(line)
        self.assertEqual((m.group("count"), m.group("set")), ("2", "1a2b3c"))
        self.assertTrue(journal.LINE_RE.match(line))

    def test_an_unsafe_agent_name_is_left_out(self):
        line = journal.format_line("2026-11-18T20:00Z", "stop", "abc1234", "main", 0, [], None, "evil files: x")
        self.assertNotIn("agent=", line)

    def test_report_lists_agents_and_reads_old_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "P-1.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Journal: P-1\n\n"
                        "- 2026-11-18T20:00Z stop abc1234 main dirty=0\n"
                        "- 2026-11-18T20:10Z stop abc1234 main dirty=0 agent=codex files: agent=fake.py\n"
                        "- 2026-11-18T20:20Z stop abc1234 main dirty=0 agent=claude-code\n"
                        "- 2026-11-18T20:30Z stop abc1234 main dirty=0 agent=codex\n")
            facts = plan.journal_facts(path)
        self.assertEqual(facts["turns"], 4)
        self.assertEqual(facts["agents"], ["codex", "claude-code"])

    def test_handoff_header_has_an_agent_line(self):
        self.assertEqual(wrapup.parse_header("# Handoff\nSession: s\nAgent: gemini\n")["agent"], "gemini")
        self.assertIsNone(wrapup.parse_header("# Handoff\nSession: s\n")["agent"])

    def test_handoff_line_names_the_agent(self):
        import datetime
        info = {"rel": "docs/project/HANDOFF.md", "related": True, "written":
                datetime.datetime(2026, 11, 18, 20, 0, tzinfo=datetime.timezone.utc), "agent": "codex"}
        self.assertIn("wrapped up 2026-11-18T20:00Z by codex", packet.handoff_line(info))
        info["agent"] = None
        self.assertNotIn(" by ", packet.handoff_line(info))


if __name__ == "__main__":
    unittest.main()
