"""Tests for the handoff write permission (P-43): `whatsnext hook permission`.

While this session's `wrap up` is open, a write to the handoff note is allowed without a prompt. Nothing else is.

Run: python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_wrapup import SID, CompactBase  # noqa: E402


class PermissionTests(CompactBase):
    def setUp(self):
        super().setUp()
        self.task()

    def wrap_up(self, session=SID):
        data = {"session_id": session, "cwd": self.proj, "prompt": "wrap up"}
        r = self.gw(["hook", "prompt-submit", "--agent", "claude-code"], stdin=json.dumps(data))
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def ask(self, target, tool="Write", session=SID):
        data = {"session_id": session, "cwd": self.proj, "tool_name": tool, "tool_input": {"file_path": target}}
        r = self.gw(["hook", "permission", "--agent", "claude-code"], stdin=json.dumps(data))
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return json.loads(r.stdout) if r.stdout.strip() else None

    def handoff(self):
        return os.path.join(self.proj, "docs", "project", "HANDOFF.md")

    def allowed(self, out):
        return out == {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}

    def test_allows_the_handoff_note_while_wrap_up_is_open(self):
        self.wrap_up()
        self.assertTrue(self.allowed(self.ask(self.handoff())))
        self.assertTrue(self.allowed(self.ask("docs/project/HANDOFF.md")))
        self.assertTrue(self.allowed(self.ask(self.handoff(), tool="Edit")))

    def test_silent_with_no_wrap_up(self):
        self.assertIsNone(self.ask(self.handoff()))

    def test_silent_for_any_other_file(self):
        self.wrap_up()
        self.assertIsNone(self.ask(os.path.join(self.proj, "src", "app.py")))
        self.assertIsNone(self.ask(os.path.join(self.proj, "docs", "project", "HANDOFF.md.bak")))
        self.assertIsNone(self.ask(os.path.join(self.proj, "docs", "..", "..", "etc", "passwd")))

    def test_silent_for_another_session_and_other_tools(self):
        self.wrap_up()
        self.assertIsNone(self.ask(self.handoff(), session="99999999-aaaa-bbbb-cccc-dddddddddddd"))
        self.assertIsNone(self.ask(self.handoff(), tool="Bash"))

    def test_follows_the_handoff_path_setting(self):
        self.cfg(paths={"handoff": ".whatsnext/sessions/custom-HANDOFF.md"})
        self.wrap_up()
        self.assertTrue(self.allowed(self.ask(os.path.join(self.proj, ".whatsnext", "sessions", "custom-HANDOFF.md"))))
        self.assertIsNone(self.ask(self.handoff()))

    def test_hooks_json_wires_it(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "hooks", "hooks.json"), encoding="utf-8") as f:
            entry = json.load(f)["hooks"]["PermissionRequest"][0]
        self.assertEqual(entry["matcher"], "Write|Edit|MultiEdit")
        self.assertIn("hook permission", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
