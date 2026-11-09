"""Tests for pruning old sessions' state files in `.whatsnext/sessions/` (ADR-0018).

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import HookBase  # noqa: E402

from wn import journal as wnjournal  # noqa: E402

OLD = time.time() - (wnjournal.SESSION_KEEP_DAYS + 1) * 86400


class PruneTests(HookBase):
    def setUp(self):
        super().setUp()
        self.cfg()
        self.folder = os.path.join(self.proj, wnjournal.SESSIONS_DIR)
        os.makedirs(self.folder, exist_ok=True)

    def session_file(self, name, old=True):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}\n")
        if old:
            os.utime(path, (OLD, OLD))
        return path

    def names(self):
        return sorted(os.listdir(self.folder))

    def test_removes_every_file_of_an_old_session(self):
        for suffix in (".json", ".handoff.json", ".compact.json", ".idle.json", ".resume.json", ".wrapup.json",
                       ".summary.json", ".summary.md", ".summary.md.bak"):
            self.session_file("old-1" + suffix)
        self.assertEqual(wnjournal.prune_sessions(self.proj), 9)
        self.assertEqual(self.names(), [])

    def test_keeps_a_session_while_any_of_its_files_is_new(self):
        self.session_file("s2.json")
        self.session_file("s2.summary.md", old=False)
        self.assertEqual(wnjournal.prune_sessions(self.proj), 0)
        self.assertEqual(self.names(), ["s2.json", "s2.summary.md"])

    def test_keeps_the_running_session(self):
        self.session_file("s1.json")
        self.assertEqual(wnjournal.prune_sessions(self.proj, keep_session="s1"), 0)
        self.assertEqual(self.names(), ["s1.json"])

    def test_never_removes_health_files_or_other_names(self):
        for name in ("health-claude-code-stop.json", "capture.unreadable.json", "notes.txt", "x-HANDOFF.md"):
            self.session_file(name)
        self.assertEqual(wnjournal.prune_sessions(self.proj), 0)
        self.assertEqual(len(self.names()), 4)

    def test_never_removes_a_link_or_prunes_through_a_linked_folder(self):
        target = self.session_file("real.json")
        os.symlink(target, os.path.join(self.folder, "link.json"))
        os.utime(os.path.join(self.folder, "link.json"), (OLD, OLD), follow_symlinks=False)
        wnjournal.prune_sessions(self.proj)
        self.assertEqual(self.names(), ["link.json"])  # the plain old file went; the link stayed
        outside = os.path.join(self.home, "elsewhere")
        os.makedirs(outside)
        with open(os.path.join(outside, "a.json"), "w", encoding="utf-8") as f:
            f.write("{}\n")
        os.utime(os.path.join(outside, "a.json"), (OLD, OLD))
        os.remove(os.path.join(self.folder, "link.json"))
        os.rmdir(self.folder)
        os.symlink(outside, self.folder)
        self.assertEqual(wnjournal.prune_sessions(self.proj), 0)
        self.assertEqual(os.listdir(outside), ["a.json"])

    def test_no_folder_is_not_an_error(self):
        os.rmdir(self.folder)
        self.assertEqual(wnjournal.prune_sessions(self.proj), 0)

    def test_session_start_prunes_and_keeps_its_own_session(self):
        self.session_file("gone.json")
        self.session_file("s1.json")
        self.hook("session-start", {"source": "startup", "session_id": "s1", "cwd": self.proj})
        names = self.names()
        self.assertNotIn("gone.json", names)
        self.assertIn("s1.json", names)


if __name__ == "__main__":
    unittest.main()
