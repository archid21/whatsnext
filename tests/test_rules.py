"""P-92 (ADR-0031): the rules preset sets rule switches; a key set in any file layer still wins."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "whatsnext", "scripts"))
from wn import config  # noqa: E402

SCRIPT = os.path.join(ROOT, "skills", "whatsnext", "scripts", "whatsnext.py")


class RulesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.proj = os.path.join(base, "proj")
        os.makedirs(os.path.join(self.proj, ".whatsnext"))
        subprocess.run(["git", "init", "-q", self.proj], check=True)
        self.xdg = os.path.join(base, "xdg")
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.xdg})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, layer, data):
        path = (os.path.join(self.xdg, "whatsnext", "config.json") if layer == "user"
                else os.path.join(self.proj, ".whatsnext", "config.json" if layer == "project" else "config.local.json"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def values(self):
        eff = config.load(self.proj)
        return eff, {k: eff.get(k) for k in ("plan.tickGuard", "plan.driftNote", "plan.branchOnStart",
                                             "plan.concurrentStart", "plan.reuseRunMax")}

    def test_standard_is_the_old_defaults(self):
        eff, v = self.values()
        self.assertEqual(v, {"plan.tickGuard": "warn", "plan.driftNote": "on", "plan.branchOnStart": "ask",
                             "plan.concurrentStart": "ask", "plan.reuseRunMax": "60m"})
        self.assertEqual(eff.source("plan.tickGuard")[0], "default")

    def test_light(self):
        self.write("user", {"rules": "light"})
        eff, v = self.values()
        self.assertEqual(v, {"plan.tickGuard": "off", "plan.driftNote": "off", "plan.branchOnStart": "stay",
                             "plan.concurrentStart": "stay", "plan.reuseRunMax": "60m"})
        self.assertEqual(eff.source("plan.tickGuard")[0], "preset: light")

    def test_strict(self):
        self.write("project", {"rules": "strict"})
        eff, v = self.values()
        self.assertEqual(v, {"plan.tickGuard": "deny", "plan.driftNote": "on", "plan.branchOnStart": "branch",
                             "plan.concurrentStart": "worktree", "plan.reuseRunMax": "15m"})

    def test_a_hand_set_key_wins_even_from_a_lower_layer(self):
        self.write("user", {"plan": {"tickGuard": "warn"}})
        self.write("local", {"rules": "strict"})
        eff, v = self.values()
        self.assertEqual(v["plan.tickGuard"], "warn")
        self.assertEqual(eff.source("plan.tickGuard")[0], "user")
        self.assertEqual(v["plan.branchOnStart"], "branch")

    def test_the_highest_layer_picks_the_preset(self):
        self.write("user", {"rules": "light"})
        self.write("project", {"rules": "strict"})
        self.assertEqual(self.values()[1]["plan.tickGuard"], "deny")

    def test_an_unknown_preset_is_an_error_and_changes_nothing(self):
        self.write("user", {"rules": "extreme"})
        eff, v = self.values()
        self.assertTrue(any("rules" in e for e in eff.errors), eff.errors)
        self.assertEqual(v["plan.tickGuard"], "warn")

    def test_config_set_and_show_name_the_preset(self):
        env = dict(os.environ, XDG_CONFIG_HOME=self.xdg)
        r = subprocess.run([sys.executable, SCRIPT, "config", "set", "--user", "rules", "light"], cwd=self.proj,
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, SCRIPT, "config", "show"], cwd=self.proj, env=env, capture_output=True, text=True)
        self.assertIn('plan.tickGuard = "off"  (preset: light)', r.stdout)


if __name__ == "__main__":
    unittest.main()


class FanOutCapTests(unittest.TestCase):
    """P-63 (ADR-0032): `plan.fanOutCap` is an integer of 1 or more, default 4."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.proj = os.path.join(base, "proj")
        os.makedirs(os.path.join(self.proj, ".whatsnext"))
        subprocess.run(["git", "init", "-q", self.proj], check=True)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(base, "xdg")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, value):
        with open(os.path.join(self.proj, ".whatsnext", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"plan": {"fanOutCap": value}}, f)

    def test_default_is_4(self):
        eff = config.load(self.proj)
        self.assertEqual(eff.get("plan.fanOutCap"), 4)
        self.assertEqual(eff.source("plan.fanOutCap")[0], "default")

    def test_valid_value_is_used(self):
        self.write(2)
        eff = config.load(self.proj)
        self.assertEqual((eff.get("plan.fanOutCap"), eff.errors), (2, []))
        self.assertEqual(eff.source("plan.fanOutCap")[0], "project")

    def test_invalid_values_fall_back_to_the_default(self):
        for bad in (0, -3, "3", 2.5, True):
            self.write(bad)
            eff = config.load(self.proj)
            self.assertEqual(eff.get("plan.fanOutCap"), 4, bad)
            self.assertEqual(len(eff.errors), 1, bad)
            self.assertIn("plan.fanOutCap", eff.errors[0])

    def test_config_set_rejects_below_one_and_non_integers(self):
        def run(value):
            return subprocess.run([sys.executable, SCRIPT, "config", "set", "--user", "plan.fanOutCap", value],
                                  cwd=self.proj, capture_output=True, text=True)
        self.assertEqual(run("3").returncode, 0)
        self.assertEqual(run("0").returncode, 2)
        self.assertEqual(run("two").returncode, 2)
