"""P-90: install-hooks backs up each file before it writes, and --undo restores the exact original bytes."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_hook_adapters import FILES, InstallBase  # noqa: E402

ORIGINAL = '{\n  "hooks": {},\n    "mine":   [1, 2,3],\n  "z": "keep my spacing"\n}\n'


class BackupTests(InstallBase):
    def each(self):
        for agent in FILES:
            with self.subTest(agent=agent):
                self.setUp()
                yield agent

    def backups(self):
        folder = os.path.join(os.path.dirname(self.env["XDG_CONFIG_HOME"]), "xdg", "whatsnext", "backups")
        return sorted(n for n in os.listdir(folder) if n != "manifest.json") if os.path.isdir(folder) else []

    def test_install_backs_up_and_undo_restores_the_exact_bytes(self):
        for agent in self.each():
            path = self.user_file(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)
            out = self.run_hooks("--agent", agent)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Backup of the previous file:", out.stdout)
            self.assertEqual(len(self.backups()), 1)
            self.assertNotEqual(self.text(path), ORIGINAL)
            self.assertEqual(self.run_hooks("--agent", agent).returncode, 0)  # a reinstall keeps the first original
            out = self.run_hooks("--agent", agent, "--undo")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("byte for byte", out.stdout)
            self.assertEqual(self.text(path), ORIGINAL)

    def test_undo_removes_a_file_install_created(self):
        for agent in self.each():
            path = self.user_file(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.assertEqual(self.run_hooks("--agent", agent).returncode, 0)
            self.assertEqual(self.backups(), [])
            self.run_hooks("--agent", agent, "--undo")
            self.assertFalse(os.path.exists(path))

    def test_a_file_changed_after_install_loses_only_our_entries_and_names_the_backup(self):
        for agent in self.each():
            path = self.user_file(agent)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(ORIGINAL)
            self.run_hooks("--agent", agent)
            data = self.read(path)
            data["added_later"] = True
            self.put(path, data)
            out = self.run_hooks("--agent", agent, "--undo")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("Original copy:", out.stdout)
            after = self.read(path)
            self.assertTrue(after["added_later"])
            self.assertNotIn("whatsnext", self.text(path))


if __name__ == "__main__":
    unittest.main()
