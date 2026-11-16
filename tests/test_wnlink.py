"""Tests for the `wn` link made by `install-hooks --user` (P-76).

Run: python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "whatsnext" / "scripts" / "whatsnext.py"
sys.path.insert(0, str(ROOT / "skills" / "whatsnext" / "scripts"))
from wn import initcmd  # noqa: E402


class WnLinkTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = os.path.join(tmp.name, "home")
        self.codex = os.path.join(self.home, ".codex")
        os.makedirs(self.codex)
        self.link = os.path.join(self.home, ".local", "bin", "wn")

    def run_hooks(self, *args):
        env = dict(os.environ, HOME=self.home, CODEX_HOME=self.codex)
        return subprocess.run([sys.executable, str(SCRIPT), "install-hooks"] + list(args), env=env,
                              cwd=self.home, capture_output=True, text=True)

    def test_asks_without_answer(self):
        r = self.run_hooks("--user")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertFalse(os.path.lexists(self.link))
        self.assertFalse(os.path.exists(os.path.join(self.codex, "hooks.json")))
        j = json.loads(self.run_hooks("--user", "--json").stdout)
        self.assertEqual((j["ask"], j["recommended"], j["answer_flag"]), ("wn_link", "link", "--wn link|skip"))

    def test_links_wn_without_codex(self):
        os.rmdir(self.codex)
        r = self.run_hooks("--user", "--wn", "link")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Codex folder not found", r.stdout)
        self.assertTrue(os.path.islink(self.link))
        self.assertFalse(os.path.exists(self.codex))
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".agents")))

    def test_link_creates_symlink_that_runs_from_another_folder(self):
        r = self.run_hooks("--wn", "link")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(self.link))
        self.assertEqual(os.path.realpath(self.link), os.path.realpath(str(SCRIPT)))
        env = dict(os.environ, HOME=self.home, CODEX_HOME=self.codex)
        out = subprocess.run([self.link, "--help"], env=env, cwd=self.home, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("install-hooks", out.stdout)
        again = self.run_hooks()  # in place: no question
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_skip_makes_no_link(self):
        r = self.run_hooks("--wn", "skip")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.link))

    def test_foreign_file_is_not_replaced(self):
        os.makedirs(os.path.dirname(self.link))
        Path(self.link).write_text("mine\n")
        r = self.run_hooks("--wn", "link")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("left as it is", r.stdout)
        self.assertEqual(Path(self.link).read_text(), "mine\n")
        self.assertFalse(os.path.islink(self.link))

    def test_remove_and_undo_remove_only_own_link(self):
        for flag in ("--remove", "--undo"):
            self.run_hooks("--wn", "link")
            self.assertTrue(os.path.islink(self.link))
            r = self.run_hooks(flag)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.lexists(self.link))
        os.symlink("/usr/bin/true", self.link)
        r = self.run_hooks("--undo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(self.link))
        self.assertEqual(os.readlink(self.link), "/usr/bin/true")

    def test_dry_run_writes_nothing(self):
        r = self.run_hooks("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("~/.local/bin/wn", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local")))
        self.assertFalse(os.path.exists(os.path.join(self.codex, "hooks.json")))

    def test_project_scope_leaves_wn_alone(self):
        root = os.path.join(self.home, "proj")
        os.makedirs(os.path.join(root, ".git"))
        env = dict(os.environ, HOME=self.home, CODEX_HOME=self.codex)
        r = subprocess.run([sys.executable, str(SCRIPT), "install-hooks", "--project"], env=env, cwd=root,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(self.link))

    def test_block_uses_wn_and_no_plugin_placeholder(self):
        text = "\n".join(initcmd.block_lines("docs/project/PLAN.md", "docs/project/progress"))
        self.assertIn("wn status", text)
        self.assertNotIn("<plugin>", text)


if __name__ == "__main__":
    unittest.main()
