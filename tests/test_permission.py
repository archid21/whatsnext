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

    def test_never_for_a_dot_folder_or_a_non_markdown_file(self):
        for rel in (".git/HANDOFF.md", ".claude/HANDOFF.md", ".github/x.md", "docs/.hidden/x.md", "docs/project/HANDOFF.sh", "../outside.md"):
            self.cfg(paths={"handoff": rel})
            self.wrap_up()
            self.assertIsNone(self.ask(os.path.join(self.proj, *rel.split("/"))), rel)

    def test_never_through_a_link(self):
        os.makedirs(os.path.join(self.proj, "docs", "project"), exist_ok=True)
        elsewhere = os.path.join(self.proj, "elsewhere.md")
        with open(elsewhere, "w", encoding="utf-8") as f:
            f.write("x\n")
        link = self.handoff()
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(elsewhere, link)
        self.wrap_up()
        self.assertIsNone(self.ask(link))
        self.assertIsNone(self.ask(elsewhere))

    def test_never_after_the_window(self):
        self.wrap_up()
        marker = os.path.join(self.proj, ".whatsnext", "sessions", SID + ".wrapup.json")
        with open(marker, encoding="utf-8") as f:
            data = json.load(f)
        data["requested_epoch"] -= 31 * 60
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIsNone(self.ask(self.handoff()))

    def test_a_relative_target_means_a_path_under_the_project_not_the_hook_cwd(self):
        self.wrap_up()
        data = {"session_id": SID, "cwd": os.path.join(self.proj, "src"), "tool_name": "Write",
                "tool_input": {"file_path": "docs/project/HANDOFF.md"}}
        r = self.gw(["hook", "permission", "--agent", "claude-code"], stdin=json.dumps(data))
        self.assertTrue(self.allowed(json.loads(r.stdout)) if r.stdout.strip() else False)

    def test_hooks_json_wires_it(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "hooks", "hooks.json"), encoding="utf-8") as f:
            entry = json.load(f)["hooks"]["PermissionRequest"][0]
        self.assertEqual(entry["matcher"], "Write|Edit|MultiEdit")
        self.assertIn("hook permission", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
