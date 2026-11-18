"""P-87 (ADR-0030): handoff `Check:` lines give VERIFIED, STALE or BROKEN; status never runs a command."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "whatsnext", "scripts"))
from wn import handoffclaims as hc, plan  # noqa: E402


def git(root, *args):
    return subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def note(*checks):
    return "# Handoff\n\n## State\nState on x: fine.\n" + "".join("Check: %s\n" % c for c in checks) + "\n## What changed\nnone\n"


class ClaimTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "one")
        self.head = git(self.root, "rev-parse", "--short", "HEAD")

    def verdicts(self, *checks, run=None):
        return [r["verdict"] for r in hc.check_all(self.root, note(*checks), run)]

    # mutation pairs: the same check, true then made false
    def test_head(self):
        self.assertEqual(self.verdicts("HEAD == " + self.head), [hc.VERIFIED])
        self.assertEqual(self.verdicts("HEAD == 0000000"), [hc.STALE])

    def test_branch(self):
        self.assertEqual(self.verdicts("branch == main"), [hc.VERIFIED])
        self.assertEqual(self.verdicts("branch == other"), [hc.STALE])

    def test_clean(self):
        self.assertEqual(self.verdicts("clean"), [hc.VERIFIED])
        open(os.path.join(self.root, "x.txt"), "w").close()
        self.assertEqual(self.verdicts("clean"), [hc.STALE])

    def test_run_pass_fail_and_broken(self):
        run = lambda c: plan.run_verify(self.root, c, 20)  # noqa: E731
        self.assertEqual(self.verdicts("run `true`", run=run), [hc.VERIFIED])
        self.assertEqual(self.verdicts("run `false`", run=run), [hc.STALE])
        self.assertEqual(self.verdicts("run `no-such-command-xyz`", run=run), [hc.BROKEN])
        self.assertEqual(self.verdicts("run `exit 126`", run=run), [hc.BROKEN])

    def test_status_never_runs_a_command(self):
        marker = os.path.join(self.root, "ran")
        self.assertEqual(self.verdicts("run `touch %s`" % marker), [hc.NOT_RUN])
        self.assertFalse(os.path.exists(marker))

    def test_unknown_form_and_no_git_are_broken(self):
        self.assertEqual(self.verdicts("tests are green"), [hc.BROKEN])
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hc.check_one(d, "HEAD == abc1234")["verdict"], hc.BROKEN)

    def test_checks_outside_state_or_in_fences_are_ignored(self):
        body = "## Next action\nCheck: clean\n## State\n```\nCheck: clean\n```\n  Check: clean\n"
        self.assertEqual(hc.checks(body), [])

    def test_line_lists_the_bad_ones(self):
        text = hc.line(hc.check_all(self.root, note("HEAD == " + self.head, "branch == other")))
        self.assertIn("1 VERIFIED, 1 STALE", text)
        self.assertIn("STALE: branch == other (branch is main)", text)


class BrokenVerifyTests(unittest.TestCase):
    def test_exit_126_127_and_timeout_are_broken_exit_1_is_not(self):
        base = {"error": None, "timed_out": False}
        self.assertTrue(plan.is_broken(dict(base, exit_code=127)))
        self.assertTrue(plan.is_broken(dict(base, exit_code=126)))
        self.assertTrue(plan.is_broken(dict(base, exit_code=None, timed_out=True)))
        self.assertFalse(plan.is_broken(dict(base, exit_code=1)))

    def test_report_counts_broken_apart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "P-1.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("- 2026-11-18T20:00Z verify failed (exit 1, 1.0 s): x\n"
                        "- 2026-11-18T20:05Z verify broken (exit 127, 1.0 s): y\n")
            facts = plan.journal_facts(path)
        self.assertEqual((facts["failed_verifies"], facts["broken_verifies"]), (1, 1))


if __name__ == "__main__":
    unittest.main()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixtures import StatusBase  # noqa: E402
from wn import packet  # noqa: E402

NOTE = ("# Handoff\n\nSession: s0\nTask: P-13\nWritten: 2026-11-05T05:03Z\nAgent: x\x1b[31mevil\n\n## Next action\nRun it.\n"
        "Verify: `test -f README.md`\n\n## State\nok\nCheck: run `touch CHECKED.txt`\nCheck: branch == \x1b[2Jx\n")


class RunCheckGateTests(StatusBase):
    """Security review of 28452db: a `run` check needs --run-checks, is listed with Verify for a tracked note,
    and note text is cleaned before it is shown."""

    def setUp(self):
        super().setUp()
        self.cfg()
        self.put("README.md", "hi\n")

    def test_run_checks_need_the_flag(self):
        self.put("docs/project/HANDOFF.md", NOTE)
        r = self.gw(["handoff", "verify"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.has("CHECKED.txt"))
        self.assertIn("not run", r.stdout)
        self.assertNotIn("\x1b", r.stdout)

    def test_run_checks_run_with_the_flag_and_are_printed_first(self):
        self.put("docs/project/HANDOFF.md", NOTE)
        r = self.gw(["handoff", "verify", "--run-checks"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has("CHECKED.txt"))
        self.assertIn("Running check: touch CHECKED.txt", r.stdout)

    def test_a_tracked_note_lists_its_run_checks_and_runs_nothing(self):
        self.put("docs/project/HANDOFF.md", NOTE)
        self.commit("track the note")
        r = self.gw(["handoff", "verify", "--run-checks"])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Read the check: touch CHECKED.txt", r.stderr)
        self.assertIn("--allow-tracked --run-checks", r.stderr)
        self.assertFalse(self.has("CHECKED.txt"))

    def test_an_unsafe_agent_header_is_dropped(self):
        self.put("docs/project/HANDOFF.md", NOTE)
        from wn import config
        info = packet.handoff_info(self.proj, config.load(self.proj), None, "s0")
        self.assertIsNone(info["agent"])
