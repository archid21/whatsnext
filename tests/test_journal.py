"""Tests for the facts journal's dirty-set digest (P-1).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import HookBase  # noqa: E402

from wn import journal as wnjournal  # noqa: E402


class DigestTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.task()
        self.commit("task")

    def note(self):
        return self.hook("session-start", {"source": "startup", "session_id": "s1"})

    def test_digest_is_a_function_of_the_names_only(self):
        self.assertEqual(wnjournal.dirty_digest(["a", "b"]), wnjournal.dirty_digest(["b", "a"]))
        self.assertNotEqual(wnjournal.dirty_digest(["a", "b"]), wnjournal.dirty_digest(["a", "c"]))
        self.assertIsNone(wnjournal.dirty_digest([]))

    def test_digest_the_journal_line_carries_it_and_a_clean_line_does_not(self):
        self.hook("stop", {"session_id": "s1"})
        self.put("src/a.py", "x\n")
        self.hook("stop", {"session_id": "s1"})
        lines = [l for l in self.get("docs/project/progress/journal/P-13.md").splitlines() if l.startswith("- ")]
        self.assertNotIn(" set=", lines[0])
        self.assertRegex(lines[1], r" dirty=1 set=[0-9a-f]{6} files: src/a.py$")
        self.assertEqual(wnjournal.last_state(self.p("docs/project/progress/journal/P-13.md"))[0], 1)

    def test_digest_same_count_but_another_file_reads_as_set_changed(self):
        self.put("src/a.py", "x\n")
        self.hook("stop", {"session_id": "s1"})
        self.assertNotIn("set changed", self.note())  # nothing moved since the stop
        os.remove(self.p("src/a.py"))
        self.put("src/b.py", "x\n")  # still one dirty file, another file
        out = self.note()
        self.assertIn("1 dirty file (src/b.py) - set changed since the last stop", out)

    def test_digest_old_lines_without_it_never_say_set_changed(self):
        os.makedirs(self.p("docs/project/progress/journal"), exist_ok=True)
        self.put("docs/project/progress/journal/P-13.md", "# Journal: P-13\n\n- 2026-11-01T10:00Z stop abc1234 master dirty=1 files: src/a.py\n")
        self.put("src/b.py", "x\n")
        self.assertNotIn("set changed", self.note())


if __name__ == "__main__":
    unittest.main()
