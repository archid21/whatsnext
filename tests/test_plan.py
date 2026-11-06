"""Tests for PLAN.md parsing, `plan` commands, claims and Start.

Run: python3 -m unittest discover -s tests
"""

import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fixtures import PLAN, PLAN_PATH, STATUS, PlanBase, Sandbox, minute_ts, task_text, ts  # noqa: E402

from wn import claims, journal, plan  # noqa: E402

# claims.short_time adds the date when the time is not today (UTC).
SHORT_TIME = r"(?:\d{4}-\d\d-\d\dT)?\d\d:\d\dZ"


class ParseTests(unittest.TestCase):
    def test_sections_fields_and_status(self):
        text = """# Plan
- [ ] X-1 Before any heading
## Now
- [ ] P-13 Add login · done means: login tests pass
- [x] P-12 Old work · done means: it works · evidence: tests pass (2026-10-27T14:05Z)
- [x] P-11 No proof · done means: it works
Some prose line.
## Next
- [ ] P-15 Password reset
- [ ] P-16 Old style - done means: works
## Notes
- [ ] N-1 In another section
"""
        lines, items = plan.parse_text(text)
        by_id = {i.id: i for i in items}
        self.assertEqual([i.id for i in items], ["X-1", "P-13", "P-12", "P-11", "P-15", "P-16", "N-1"])
        self.assertEqual(by_id["X-1"].section, "Other")
        self.assertEqual(by_id["P-13"].section, "Now")
        self.assertEqual((by_id["P-13"].title, by_id["P-13"].done_means, by_id["P-13"].checked),
                         ("Add login", "login tests pass", False))
        self.assertEqual((by_id["P-12"].checked, by_id["P-12"].evidence), (True, "tests pass (2026-10-27T14:05Z)"))
        self.assertEqual((by_id["P-11"].checked, by_id["P-11"].evidence), (True, ""))
        self.assertEqual(by_id["P-15"].section, "Next")
        self.assertEqual(by_id["P-15"].done_means, "")
        self.assertEqual((by_id["P-16"].title, by_id["P-16"].done_means), ("Old style", "works"))
        self.assertEqual(by_id["N-1"].section, "Other")

    def test_comments_are_ignored(self):
        text = """## Now
<!-- - [ ] P-1 Hidden one -->
- [ ] P-2 Visible <!-- note --> · done means: yes
<!--
- [ ] P-3 Hidden in a long comment
-->
- [ ] P-4 After
"""
        _lines, items = plan.parse_text(text)
        self.assertEqual([i.id for i in items], ["P-2", "P-4"])
        self.assertEqual(items[0].title, "Visible")
        self.assertEqual(items[0].done_means, "yes")

    def test_non_items_are_not_items(self):
        text = "## Now\n- [ ] p-1 lowercase\n- [ ] P13 no dash\n- [ ]P-5 no space\n- plain bullet\n- [ ] P-6 ok\n"
        self.assertEqual([i.id for i in plan.parse_text(text)[1]], ["P-6"])

    def test_write_changes_only_one_line_and_keeps_crlf(self):
        import tempfile

        text = "# Plan\r\n\r\n## Now\r\n- [ ] P-13 Add login · done means: ok\r\nprose\r\n- [ ] P-14 Other\r\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "PLAN.md")
            with open(path, "w", newline="") as f:
                f.write(text)
            self.assertTrue(plan.rewrite_item(path, "P-14", lambda line: plan.with_field(line, "done means: yes")))
            self.assertFalse(plan.rewrite_item(path, "P-99", lambda line: line))
            with open(path, newline="") as f:
                after = f.read()
        self.assertEqual(after, text.replace("- [ ] P-14 Other\r\n", "- [ ] P-14 Other · done means: yes\r\n"))

    def test_evidence_goes_after_done_means(self):
        line = "- [x] P-1 T · evidence: e (t)"
        self.assertEqual(plan.with_field(line, "done means: d"), "- [x] P-1 T · done means: d · evidence: e (t)")


class ListNextTests(PlanBase):
    def test_list_text_and_json_show_status_and_claim(self):
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-16 Audit log", "- [x] P-16 Audit log · done means: x · evidence: verified: true passed in 1 s (t)")
                 + "- [x] P-17 Unproven\n")
        self.set_claim("P-14", agent="codex", since=ts(60), updated=ts(5), branch="p-14-rate")
        self.put("%s/P-15.md" % STATUS, task_text("P-15", state="blocked"))
        r = self.plan("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual([l for l in lines if not l.startswith(" ")],
                         ["Now", "Next", "Later", "* checked by a person, not verified"])
        self.assertIn("P-13  Add login  [open]", r.stdout)
        self.assertRegex(r.stdout, r"P-14  Rate-limit the API  \[in progress \(codex · p-14-rate · since %s\)\]" % SHORT_TIME)
        self.assertIn("[blocked]", r.stdout)
        self.assertIn("[done]", r.stdout)
        self.assertIn("P-17  Unproven  [done*]", r.stdout)
        self.assertNotIn("[done (", r.stdout)
        _r, data = self.jplan("list")
        rows = {v["id"]: v for v in data["items"]}
        self.assertEqual(rows["P-14"]["status"], "in progress")
        self.assertEqual(rows["P-14"]["claim"]["agent"], "codex")
        self.assertFalse(rows["P-14"]["claim"]["stale"])
        self.assertEqual(rows["P-15"]["status"], "blocked")
        self.assertIs(rows["P-16"]["verified"], True)
        self.assertIs(rows["P-17"]["verified"], False)

    def test_plain_plan_lists(self):
        self.assertIn("Now", self.plan().stdout)

    def test_unverified_footnote_once_and_only_when_needed(self):
        footnote = "* checked by a person, not verified"
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-16 Audit log", "- [x] P-16 Audit log · done means: x · evidence: verified: true passed in 1 s (t)"))
        r = self.plan("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(footnote, r.stdout)
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-13", "- [x] P-13") + "- [x] P-17 Unproven\n")
        r = self.plan("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("[done*]"), 2)
        self.assertEqual(r.stdout.count(footnote), 1)
        self.assertEqual(r.stdout.splitlines()[-1], footnote)

    def test_next_order_now_then_stale_then_next(self):
        self.cfg(plan={"staleAfter": "30m"})
        r, data = self.jplan("next")
        self.assertEqual([c["id"] for c in data["candidates"]], ["P-13", "P-14"])
        self.assertEqual(data["recommended"], "P-13")
        self.assertEqual([c["source"] for c in data["candidates"]], ["Now", "Now"])
        # P-13 claimed and fresh: skipped. P-14 claimed and stale: listed, marked stale.
        self.set_claim("P-13", updated=ts(5))
        self.set_claim("P-14", updated=ts(120))
        r, data = self.jplan("next")
        self.assertEqual([c["id"] for c in data["candidates"]], ["P-14"])
        self.assertTrue(data["candidates"][0]["stale"])
        self.assertIn("stale", self.plan("next").stdout)
        # a fresh open item comes before a stale one
        self.put(PLAN_PATH, PLAN.replace("## Next", "- [ ] P-20 Third in Now\n## Next"))
        _r, data = self.jplan("next")
        self.assertEqual([c["id"] for c in data["candidates"]], ["P-20", "P-14"])

    def test_next_falls_back_to_next_and_skips_done_and_blocked(self):
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-13", "- [x] P-13").replace("- [ ] P-14", "- [ ] P-14")
                 .replace("## Next", "- [ ] P-17 Blocked one\n## Next").replace("- [ ] P-15", "- [ ] P-18 Dup next\n- [ ] P-15"))
        self.set_claim("P-14", updated=ts(1))
        self.put("%s/P-17.md" % STATUS, task_text("P-17", state="blocked"))
        r = self.plan("next")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1. P-18 Dup next  [from Next; recommended]", r.stdout)
        self.assertIn("2. P-15 Password reset", r.stdout)
        self.assertNotIn("P-16", r.stdout)  # Later is never offered
        self.assertNotIn("P-17", r.stdout)

    def test_next_limit_and_nothing_available(self):
        _r, data = self.jplan("next", "--limit", "1")
        self.assertEqual(len(data["candidates"]), 1)
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-1", "- [x] P-1").replace("- [ ] P-1", "- [x] P-1"))
        r = self.plan("next")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "Nothing open in Now or Next."))
        _r, data = self.jplan("next")
        self.assertEqual((data["candidates"], data["recommended"], data["message"]), ([], None, "Nothing open in Now or Next."))

    HANDOFF = ("# Handoff\n\nSession: abc-123\nTask: none\nWritten: 2026-11-06T22:56Z\n\n## Goal\n\nShip it.\n\n"
               "## Next action\n\nRun doctor.\nVerify: `true`\n\n## Open questions and blockers\n\n"
               "Push main? Codex hooks not run.\n")

    def test_next_shows_handoff_when_plan_is_empty(self):
        self.put("docs/project/HANDOFF.md", self.HANDOFF)
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-1", "- [x] P-1"))
        r = self.plan("next")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("Nothing open in Now or Next."), r.stdout)
        self.assertIn("Handoff: docs/project/HANDOFF.md, written 2026-11-06T22:56Z (Fri 2026-11-06 2:56 PM PST)", r.stdout)
        self.assertIn("Next action: Run doctor. Verify: `true`", r.stdout)
        self.assertIn("Open questions and blockers: Push main? Codex hooks not run.", r.stdout)
        _r, data = self.jplan("next")
        self.assertEqual(data["message"], "Nothing open in Now or Next.")
        self.assertEqual(data["handoff"]["path"], "docs/project/HANDOFF.md")
        self.assertEqual(data["handoff"]["written"], "2026-11-06T22:56Z")
        self.assertEqual(data["handoff"]["next_action"], "Run doctor. Verify: `true`")
        self.assertEqual(data["handoff"]["open_questions"], "Push main? Codex hooks not run.")

    def test_next_shows_handoff_below_open_items_and_skips_it_when_none_or_empty(self):
        r = self.plan("next")
        self.assertNotIn("Handoff:", r.stdout)
        _r, data = self.jplan("next")
        self.assertIsNone(data["handoff"])
        self.put("docs/project/HANDOFF.md", self.HANDOFF)
        r = self.plan("next")
        self.assertTrue(r.stdout.startswith("Next up:"), r.stdout)
        self.assertLess(r.stdout.index("1. P-13"), r.stdout.index("Handoff:"))
        self.put("docs/project/HANDOFF.md", "# Handoff\n\nSession: s\nTask: none\nWritten: 2026-11-06T22:56Z\n\n"
                 "## Open questions and blockers\n\nnone\n")
        self.assertNotIn("Open questions and blockers", self.plan("next").stdout)

    def test_missing_plan_file(self):
        os.remove(self.p(PLAN_PATH))
        for args in (["list"], ["next"]):
            r = self.plan(*args)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "No plan file at %s." % PLAN_PATH))
        self.assertEqual(self.plan("start", "P-13").returncode, 1)

    def test_check(self):
        r = self.plan("check")
        self.assertEqual(r.returncode, 0)
        self.assertIn('warning: P-16 has no "done means".', r.stdout)
        self.put(PLAN_PATH, PLAN + "- [x] P-20 No proof · done means: x\n- [ ] P-13 Again · done means: x\n")
        r = self.plan("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: P-13 appears 2 times.", r.stdout)
        self.assertIn("warning: P-20 is checked without evidence", r.stdout)
        _r, data = self.jplan("check")
        self.assertEqual(data["errors"], ["P-13 appears 2 times."])
        self.put(PLAN_PATH, "## Now\n- [ ] P-1 A · done means: `true` passes\n")
        self.assertEqual(self.plan("check").stdout.strip(), "%s is fine." % PLAN_PATH)


class ClaimTests(PlanBase):
    def test_claim_is_in_git_common_dir_and_seen_from_a_worktree(self):
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.claim_data("P-13")
        self.assertEqual((data["id"], data["agent"], data["branch"]), ("P-13", "codex", self.branch()))
        self.assertEqual(data["worktree"], os.path.realpath(self.proj))
        self.assertIsNone(data["asked_at"])
        self.assertTrue(data["token"])
        self.assertEqual(self.git("status", "--porcelain", "--", ".git"), "")
        wt = os.path.join(os.path.dirname(self.proj), "second")
        self.git("worktree", "add", "-q", wt, "-b", "other")
        r = self.plan("list", cwd=wt)
        self.assertRegex(r.stdout, r"P-13  Add login  \[in progress \(codex")
        _r, data = self.jplan("next", cwd=wt)
        self.assertEqual([c["id"] for c in data["candidates"]], ["P-14"])
        # the second worktree is another claimant: starting P-13 there asks for a takeover
        q = self.question(self.start("P-13", "--json", cwd=wt, agent="claude-code"))
        self.assertEqual(q["ask"], "takeover")

    def test_claim_outside_git_goes_to_groundwork_dir(self):
        c = claims.claims_dir(self.proj)
        self.assertEqual(c, os.path.join(os.path.realpath(self.proj), ".git", "whatsnext", "claims"))
        self.assertEqual(claims.claims_dir(os.path.join(self.tmp.name, "nowhere")),
                         os.path.join(self.tmp.name, "nowhere", ".whatsnext", "claims"))

    def test_existing_claim_of_another_needs_takeover(self):
        self.set_claim("P-13", agent="codex")
        got, other = claims.claim(self.proj, "P-13", "claude-code")
        self.assertIsNone(got)
        self.assertEqual(other["token"], "other-token")
        self.assertEqual(self.claim_data("P-13")["token"], "other-token")
        got, other = claims.claim(self.proj, "P-13", "claude-code", takeover=True)
        self.assertEqual((got["agent"], other), ("claude-code", None))
        self.assertNotEqual(self.claim_data("P-13")["token"], "other-token")

    def test_write_then_read_back_detects_a_lost_race(self):
        real = claims._write_new

        def racing(path, data):
            ok = real(path, data)
            other = dict(data, agent="codex", token="someone-else")
            claims._write_replace(path, other)  # another process wrote right after us
            return ok

        claims._write_new = racing
        try:
            got, other = claims.claim(self.proj, "P-13", "claude-code")
        finally:
            claims._write_new = real
        self.assertIsNone(got)
        self.assertEqual(other["agent"], "codex")

    def test_same_claimant_rerun_keeps_since(self):
        got, _ = claims.claim(self.proj, "P-13", "codex")
        self.set_claim("P-13", agent="codex", since="2026-10-01T10:00:00Z", updated=ts(10))
        again, other = claims.claim(self.proj, "P-13", "codex")
        self.assertEqual((again["since"], other), ("2026-10-01T10:00:00Z", None))

    def test_stale_uses_the_later_of_claim_and_status_times(self):
        self.cfg(plan={"staleAfter": "30m"})
        eff = plan.gwconfig.load(self.proj)
        self.assertEqual(eff.get("plan.staleAfter"), "30m")
        claim = {"updated": ts(60)}
        self.assertTrue(claims.is_stale(claim, None, "30m"))
        self.assertTrue(claims.is_stale(claim, minute_ts(45), "30m"))
        self.assertFalse(claims.is_stale(claim, minute_ts(10), "30m"))  # a recent status write
        self.assertFalse(claims.is_stale({"updated": ts(10)}, minute_ts(120), "30m"))
        self.assertFalse(claims.is_stale({"updated": ts(60)}, None, "4h"))
        self.assertEqual(claims.stale_delta("4h"), datetime.timedelta(hours=4))
        self.assertEqual(claims.stale_delta("30m"), datetime.timedelta(minutes=30))
        self.assertEqual(claims.stale_delta("bad"), datetime.timedelta(hours=4))

    def test_list_marks_stale_with_the_config_value(self):
        self.cfg(plan={"staleAfter": "30m"})
        self.set_claim("P-13", updated=ts(90), since=ts(300))
        _r, data = self.jplan("list")
        row = data["items"][0]
        self.assertTrue(row["claim"]["stale"])
        self.assertIn("stale, idle since", self.plan("list").stdout)
        self.cfg(plan={"staleAfter": "4h"})
        self.assertFalse(self.jplan("list")[1]["items"][0]["claim"]["stale"])

    def test_status_stamp_refreshes_the_claim(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.set_claim("P-13", updated=ts(300), asked_at=ts(10), since=ts(400))
        self.assertEqual(self.gw(["progress", "stamp", "P-13"]).returncode, 0)
        data = self.claim_data("P-13")
        self.assertGreater(data["updated"], ts(2)[:-4])
        self.assertIsNone(data["asked_at"])

    def test_keep_and_release(self):
        r = self.plan("keep", "P-13")
        self.assertEqual(r.returncode, 1)
        self.set_claim("P-13", updated=ts(300), asked_at=ts(10))
        r = self.plan("keep", "P-13")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = self.claim_data("P-13")
        self.assertGreater(data["updated"], ts(2)[:-4])
        self.assertIsNone(data["asked_at"])
        r = self.plan("put-back", "P-13", "--saved")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.has_claim("P-13"))
        self.assertEqual([e["payload"]["id"] for e in self.evs("task.release")], ["P-13"])
        self.assertEqual(self.plan("put-back", "P-13", "--saved").returncode, 1)
        self.assertIn("[open]", self.plan("list").stdout)


class PutBackTests(PlanBase):
    """Putting an item back saves its progress first and records where the work was left (ADR-0002)."""

    def field(self, text, name):
        line = next((l for l in text.splitlines() if l.startswith("- **%s:** " % name)), None)
        return line[len("- **%s:** " % name):] if line else None

    def test_put_back_asks_to_save_first_and_changes_nothing(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        before = self.get("%s/P-13.md" % STATUS)
        q = self.question(self.plan("put-back", "P-13", "--json"))
        self.assertEqual((q["ask"], q["answer_flag"]), ("save_first", "--saved"))
        self.assertIn("update docs/project/progress/P-13.md: Done (with evidence), In progress", q["question"])
        self.assertTrue(self.has_claim("P-13"))
        self.assertEqual(self.get("%s/P-13.md" % STATUS), before)

    def test_saved_put_back_records_where_the_work_was_left(self):
        self.assertEqual(self.start("P-13", "--branch", "branch").returncode, 0)
        self.put("app.py", "x = 1\n")
        self.put("README.md", "changed\n")
        r = self.plan("put-back", "P-13", "--saved")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Left at: branch p-13-add-login at ", r.stdout)
        text = self.get("%s/P-13.md" % STATUS)
        self.assertEqual(self.field(text, "State"), "parked")
        left = self.field(text, "Left at")
        self.assertRegex(left, r"^branch p-13-add-login at [0-9a-f]{7,}; 2 uncommitted files \((README.md, app.py|app.py, README.md)\) "
                               r"\(put back \d{4}-\d\d-\d\dT\d\d:\d\dZ\)$")
        self.assertNotIn("worktree", left)
        self.assertFalse(self.has_claim("P-13"))
        self.assertIn("[open]", self.plan("list").stdout)

    def test_start_again_shows_the_earlier_work_and_recommends_its_branch(self):
        self.assertEqual(self.start("P-13", "--branch", "branch").returncode, 0)
        self.plan("put-back", "P-13", "--saved")
        self.git("switch", "-q", "-")
        q = self.question(self.start("P-13", "--agent", "claude-code", "--json"))
        self.assertEqual(q["ask"], "branch")
        self.assertEqual(q["recommended"], "branch")
        self.assertIn("where the earlier work is", q["options"][0]["description"])
        self.assertIn("branch p-13-add-login", q["context"]["earlier_work"])
        r = self.start("P-13", "--branch", "branch", agent="claude-code")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Earlier work: branch p-13-add-login at ", r.stdout)
        self.assertEqual(self.field(self.get("%s/P-13.md" % STATUS), "State"), "active")

    def test_worktree_put_back_copies_the_status_file_home_and_start_continues_there(self):
        r, data = self.jplan("start", "P-13", "--agent", "codex", "--branch", "worktree")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wt = data["worktree"]
        self.assertFalse(self.has("%s/P-13.md" % STATUS))  # the progress file moved to the worktree
        with open(os.path.join(wt, "work.py"), "w") as f:
            f.write("y = 2\n")
        r = self.plan("put-back", "P-13", "--saved", cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        home = self.get("%s/P-13.md" % STATUS)  # now also in the main folder
        left = self.field(home, "Left at")
        self.assertIn("1 uncommitted file (work.py)", left)
        self.assertIn("in worktree %s" % wt, left)
        # A different agent, starting from the main folder, sees it and is offered the same worktree.
        q = self.question(self.start("P-13", "--agent", "claude-code", "--json"))
        self.assertEqual(q["recommended"], "worktree")
        self.assertEqual(q["options"][2]["label"], "Existing worktree")
        r, data = self.jplan("start", "P-13", "--agent", "claude-code", "--branch", "worktree")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(data["worktree"], wt)
        self.assertIn("in worktree", data["earlier_work"])
        self.assertEqual(self.claim_data("P-13")["agent"], "claude-code")
        with open(os.path.join(wt, STATUS, "P-13.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual((self.field(text, "State"), self.field(text, "Agent")), ("active", "claude-code"))

    def test_start_putting_back_the_current_item_asks_to_save_it_first(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        q = self.question(self.start("P-14", "--current", "put-back", "--json"))
        self.assertEqual((q["ask"], q["context"]["id"]), ("save_first", "P-13"))
        self.assertTrue(self.has_claim("P-13"))
        self.assertFalse(self.has_claim("P-14"))
        r = self.start("P-14", "--current", "put-back", "--saved", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.field(self.get("%s/P-13.md" % STATUS), "State"), "parked")


class StartChecksTests(PlanBase):
    def nothing_changed(self, item="P-13"):
        self.assertFalse(self.has_claim(item))
        self.assertFalse(self.has("%s/%s.md" % (STATUS, item)))
        self.assertEqual(self.get(PLAN_PATH), PLAN)
        self.assertEqual(self.evs("task.start"), [])

    def test_unknown_done_and_blocked_items_are_refused(self):
        self.assertEqual(self.start("P-99").returncode, 1)
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-13", "- [x] P-13"))
        r = self.start("P-13")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already done", r.stderr)
        self.put("%s/P-14.md" % STATUS, task_text("P-14", state="blocked"))
        r = self.start("P-14")
        self.assertEqual(r.returncode, 1)
        self.assertIn("blocked", r.stderr)
        self.assertFalse(self.has_claim("P-14"))

    def test_takeover_question_and_flag(self):
        self.set_claim("P-13", agent="codex", since=ts(30), updated=ts(20))
        r = self.start("P-13", "--json", agent="claude-code")
        q = self.question(r)
        self.assertEqual(q["ask"], "takeover")
        self.assertRegex(q["question"], r"^codex has had P-13 in progress since %s \(idle since %s\)\. Take it over\?$" % (SHORT_TIME, SHORT_TIME))
        self.assertEqual([o["value"] for o in q["options"]], ["yes", "no"])
        self.assertEqual(q["recommended"], "no")
        self.assertEqual(q["context"]["claim"]["agent"], "codex")
        self.assertEqual(self.claim_data("P-13")["token"], "other-token")
        text = self.start("P-13", agent="claude-code")
        self.assertEqual(text.returncode, 4)
        self.assertIn("Question (takeover):", text.stdout)
        self.assertIn("--takeover", text.stdout)
        r = self.start("P-13", "--takeover", "--branch", "stay", agent="claude-code")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.claim_data("P-13")["agent"], "claude-code")

    def test_takeover_of_a_stale_claim_is_recommended(self):
        self.cfg(plan={"staleAfter": "30m"})
        self.set_claim("P-13", updated=ts(300))
        self.assertEqual(self.question(self.start("P-13", "--json", agent="claude-code"))["recommended"], "yes")

    def test_missing_done_means_question_and_flag(self):
        q = self.question(self.start("P-16", "--json"))
        self.assertEqual((q["ask"], q["options"], q["context"]["id"]), ("done_means", [], "P-16"))
        self.assertTrue(q["free_text"])
        self.assertFalse(self.has_claim("P-16"))
        self.assertEqual(self.get(PLAN_PATH), PLAN)
        r = self.start("P-16", "--done-means", "audit rows exist", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("- [ ] P-16 Audit log · done means: audit rows exist\n", self.get(PLAN_PATH))
        self.assertIn("Done means: audit rows exist", self.get(STATUS + "/P-16.md"))
        self.assertEqual(self.get(PLAN_PATH).replace(" · done means: audit rows exist", ""), PLAN)

    def test_uncommitted_question_and_nothing_claimed(self):
        self.put("src/other.py", "x = 1\n")
        q = self.question(self.start("P-13", "--json"))
        self.assertEqual(q["ask"], "uncommitted")
        self.assertEqual([o["value"] for o in q["options"]], ["commit", "stash", "carry-on"])
        self.assertEqual(q["recommended"], "commit")
        self.assertEqual(q["context"]["files"], ["src/other.py"])
        self.nothing_changed()

    def test_groundwork_own_files_are_not_uncommitted_work(self):
        self.put(STATUS + "/P-99.md", task_text("P-99"))
        self.put(PLAN_PATH, PLAN + "\n")
        self.put(".whatsnext/notes.txt", "x")
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dirty_commit_asks_to_commit_first(self):
        self.put("src/other.py", "x = 1\n")
        q = self.question(self.start("P-13", "--dirty", "commit", "--json"))
        self.assertEqual(q["ask"], "commit_first")
        self.assertFalse(self.has_claim("P-13"))
        self.assertTrue(self.has("src/other.py"))
        self.commit("other work")
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)

    def test_dirty_stash_stashes_only_other_work(self):
        self.put("src/other.py", "x = 1\n")
        self.put(PLAN_PATH, PLAN + "\n")  # the plan file stays put
        r = self.start("P-13", "--dirty", "stash", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.has("src/other.py"))
        self.assertTrue(self.get(PLAN_PATH).endswith("\n\n"))
        self.assertIn("whatsnext: before P-13", self.git("stash", "list"))
        self.assertTrue(self.has_claim("P-13"))

    def test_dirty_carry_on_leaves_the_files(self):
        self.put("src/other.py", "x = 1\n")
        r = self.start("P-13", "--dirty", "carry-on", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has("src/other.py"))
        self.assertEqual(self.git("stash", "list"), "")


class CurrentItemTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)

    def test_question_recommends_done_without_unfinished_work(self):
        q = self.question(self.start("P-14", "--json"))
        self.assertEqual(q["ask"], "current_item")
        self.assertEqual([o["value"] for o in q["options"]], ["done", "keep", "put-back"])
        self.assertEqual(q["recommended"], "done")
        self.assertEqual(q["context"]["id"], "P-13")
        self.assertFalse(q["context"]["has_unfinished_work"])
        self.assertFalse(self.has_claim("P-14"))

    def test_question_recommends_keep_with_unfinished_work(self):
        path = STATUS + "/P-13.md"
        self.put(path, self.get(path).replace("## In progress\n", "## In progress\n\nHalf-written login form.\n"))
        q = self.question(self.start("P-14", "--json"))
        self.assertEqual((q["recommended"], q["context"]["has_unfinished_work"]), ("keep", True))

    def test_done_needs_evidence_then_marks_it(self):
        q = self.question(self.start("P-14", "--current", "done", "--json"))
        self.assertEqual(q["ask"], "evidence")
        self.assertTrue(self.has_claim("P-13"))
        r = self.start("P-14", "--current", "done", "--evidence", "tests pass", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(self.get(PLAN_PATH), r"- \[x\] P-13 Add login · done means: login tests pass · evidence: tests pass \(\d{4}-\d\d-\d\dT\d\d:\d\dZ\)\n")
        self.assertFalse(self.has_claim("P-13"))
        self.assertTrue(self.has_claim("P-14"))
        self.assertIn("- **State:** done\n", self.get(STATUS + "/P-13.md"))
        self.assertEqual(len(self.evs("task.done")), 1)

    def test_done_unverified(self):
        r = self.start("P-14", "--current", "done", "--unverified", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("evidence: checked by a person, not verified (", self.get(PLAN_PATH))

    def test_keep_and_release(self):
        r = self.start("P-14", "--current", "keep", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has_claim("P-13") and self.has_claim("P-14"))
        self.plan("put-back", "P-14", "--saved")
        self.plan("put-back", "P-13", "--saved")
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        r = self.start("P-14", "--current", "put-back", "--saved", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.has_claim("P-13"))
        self.assertTrue(self.has_claim("P-14"))
        self.assertEqual(len(self.evs("task.release")), 3)  # two manual releases and this one

    def test_nothing_changes_while_the_question_is_open(self):
        before = self.get(PLAN_PATH)
        self.question(self.start("P-14", "--json"))
        self.assertEqual(self.get(PLAN_PATH), before)
        self.assertFalse(self.has("%s/P-14.md" % STATUS))


class BranchTests(PlanBase):
    def test_branch_question_after_the_claim(self):
        q = self.question(self.start("P-13", "--json"))
        self.assertEqual(q["ask"], "branch")
        self.assertEqual([o["value"] for o in q["options"]], ["branch", "stay", "worktree"])
        self.assertEqual(q["recommended"], "branch")  # on the default branch
        self.assertEqual(q["context"]["branch_name"], "p-13-add-login")
        self.assertEqual(q["context"]["default"], self.branch())
        self.assertTrue(q["context"]["claimed"])
        self.assertTrue(self.has_claim("P-13"))
        self.assertTrue(self.has("%s/P-13.md" % STATUS))
        self.assertEqual(len(self.evs("task.start")), 1)
        text = self.start("P-13")
        self.assertEqual(text.returncode, 4)
        self.assertIn("Question (branch):", text.stdout)
        self.assertIn("(recommended)", text.stdout)

    def test_recommends_stay_off_the_default_branch_and_worktree_with_another_agent(self):
        self.git("switch", "-q", "-c", "feature")
        self.assertEqual(self.question(self.start("P-13", "--json"))["recommended"], "stay")
        self.plan("put-back", "P-13", "--saved")
        self.set_claim("P-14", agent="claude-code")
        self.assertEqual(self.question(self.start("P-13", "--current", "keep", "--json"))["recommended"], "worktree")

    def test_rerun_with_the_answer_is_idempotent(self):
        self.assertEqual(self.start("P-13").returncode, 4)
        since = self.claim_data("P-13")["since"]
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.claim_data("P-13")["since"], since)
        self.assertEqual(len(self.evs("task.start")), 1)  # the rerun is not a second start
        self.assertEqual(self.branch(), self.git("symbolic-ref", "--short", "HEAD"))

    def test_branch_creates_from_default(self):
        r, data = self.jplan("start", "P-13", "--agent", "codex", "--branch", "branch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.branch(), "p-13-add-login")
        self.assertEqual((data["branch"], data["branch_action"], data["worktree"]), ("p-13-add-login", "branch", None))
        self.assertTrue(data["started"])
        self.assertEqual(data["done_means"], "login tests pass")
        self.assertEqual(data["progress_file"], "%s/P-13.md" % STATUS)
        self.assertIn("wait for the user's OK before changing files", data["next_step"])
        self.assertIn("- **Branch:** p-13-add-login\n", self.get("%s/P-13.md" % STATUS))
        self.assertEqual(self.claim_data("P-13")["branch"], "p-13-add-login")

    def test_branch_starts_from_the_default_not_the_current_branch(self):
        base = self.branch()
        self.git("switch", "-q", "-c", "side")
        self.put("side.txt", "x")
        self.commit("side work")
        r = self.start("P-13", "--branch", "branch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.git("rev-parse", base))

    def test_stay(self):
        base = self.branch()
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.branch(), base)
        self.assertIn("- **Branch:** %s\n" % base, self.get("%s/P-13.md" % STATUS))
        self.assertIn("Branch: %s" % base, r.stdout)

    def test_worktree(self):
        r, data = self.jplan("start", "P-13", "--agent", "codex", "--branch", "worktree")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wt = os.path.join(os.path.dirname(os.path.realpath(self.proj)), "proj-p-13")
        self.assertEqual(data["worktree"], wt)
        self.assertTrue(os.path.isdir(wt))
        self.assertIn(wt, self.git("worktree", "list"))
        self.assertEqual(self.git("-C", wt, "symbolic-ref", "--short", "HEAD"), "p-13-add-login")
        self.assertEqual(self.branch(), self.git("symbolic-ref", "--short", "HEAD"))
        self.assertNotEqual(self.branch(), "p-13-add-login")
        self.assertEqual(self.claim_data("P-13")["worktree"], wt)
        self.assertTrue(os.path.isfile(os.path.join(wt, STATUS, "P-13.md")))
        self.assertFalse(self.has("%s/P-13.md" % STATUS))
        with open(os.path.join(wt, STATUS, "P-13.md"), encoding="utf-8") as f:
            self.assertIn("- **Branch:** p-13-add-login\n", f.read())
        text = self.plan("start", "P-14", "--agent", "codex", "--branch", "worktree")
        self.assertEqual(text.returncode, 0, text.stdout + text.stderr)
        self.assertIn("Tell the user to open this folder", text.stdout)

    def test_skip_when_already_on_the_items_branch(self):
        self.git("switch", "-q", "-c", "p-13-add-login")
        r = self.start("P-13")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Branch: p-13-add-login", r.stdout)
        self.assertNotIn("(new)", r.stdout)

    def test_setting_replaces_the_question(self):
        self.cfg(plan={"branchOnStart": "stay"})
        r = self.start("P-13")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.cfg(plan={"branchOnStart": "branch"})
        r = self.start("P-14")
        self.assertEqual(r.returncode, 4)  # the current item question comes first
        r = self.start("P-14", "--current", "keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.branch(), "p-14-rate-limit-the-api")

    def test_always_saves_to_config_local(self):
        self.write("local", {"capture": {"keywords": ["we decided"]}})
        r = self.start("P-13", "--branch", "stay", "--always")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.p(".whatsnext/config.local.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["plan"], {"branchOnStart": "stay"})
        self.assertEqual(data["capture"], {"keywords": ["we decided"]})
        self.assertIn("plan.branchOnStart = \"stay\"  (local", self.gw(["config", "show"]).stdout)

    def test_always_does_not_overwrite_a_broken_local_file(self):
        self.write("local", "{not json", raw=True)
        r = self.start("P-13", "--branch", "stay", "--always")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("not saving plan.branchOnStart", r.stderr)
        self.assertEqual(self.get(".whatsnext/config.local.json"), "{not json")

    def test_status_file_is_created_with_goal_and_first_step(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        text = self.get("%s/P-13.md" % STATUS)
        self.assertTrue(text.startswith("format: 2\n\n# P-13: Add login\n"))
        self.assertIn("- **State:** active\n", text)
        self.assertIn("- **Agent:** codex\n", text)
        self.assertIn("## Next action\n\nRestate the goal and done means, list 3 to 5 steps, and wait for the user's OK.\n", text)
        self.assertIn("## Goal\n\nAdd login\nDone means: login tests pass\n", text)
        started = self.evs("task.start")
        self.assertEqual(started[0]["payload"], {"id": "P-13", "agent": "codex", "branch": self.branch()})

    def test_existing_status_file_is_set_active(self):
        self.put("%s/P-13.md" % STATUS, task_text("P-13", state="parked", next_action="Keep this text."))
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        text = self.get("%s/P-13.md" % STATUS)
        self.assertIn("- **State:** active\n", text)
        self.assertIn("Keep this text.", text)
        self.assertIn("- **Agent:** codex\n", text)

    def test_name_slug_is_short(self):
        self.assertEqual(plan.item_branch("P-13", "Add login"), "p-13-add-login")
        name = plan.item_branch("P-1", "A very long title " * 10)
        self.assertLessEqual(len(name), 40 + 4)
        self.assertFalse(name.endswith("-"))
        self.assertEqual(plan.item_branch("P-2", "***"), "p-2")


class NoGitTests(Sandbox):
    git = False

    def test_start_skips_the_branch_step_outside_git(self):
        os.makedirs(os.path.join(self.proj, "docs", "project"))
        with open(os.path.join(self.proj, PLAN_PATH), "w", encoding="utf-8") as f:
            f.write(PLAN)
        r = self.gw(["plan", "start", "P-13", "--agent", "codex", "--json"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual((data["branch"], data["branch_action"]), (None, "skipped"))
        claim_file = os.path.join(self.proj, ".whatsnext", "claims", "P-13.json")
        self.assertTrue(os.path.isfile(claim_file))
        r = self.gw(["plan", "next"])
        self.assertIn("1. P-14", r.stdout)


class ClaimFallbackTests(PlanBase):
    """When the git folder cannot be written (Codex's sandbox), claims go to .whatsnext/claims/."""

    def setUp(self):
        super().setUp()
        self.primary = os.path.dirname(self.claim_path("P-13"))
        os.makedirs(self.primary, exist_ok=True)
        os.chmod(self.primary, 0o500)
        self.addCleanup(lambda: os.chmod(self.primary, 0o700))
        self.fallback = os.path.join(self.proj, ".whatsnext", "claims")

    def test_start_falls_back_and_the_claim_is_found_and_hidden_from_git(self):
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.fallback, "P-13.json")))
        self.assertFalse(os.path.exists(os.path.join(self.primary, "P-13.json")))
        self.assertNotIn("[open]", [l for l in self.plan("list").stdout.splitlines() if "P-13" in l][0])
        kept = self.plan("keep", "P-13")
        self.assertEqual(kept.returncode, 0, kept.stdout + kept.stderr)
        status = self.git("status", "--porcelain", "--untracked-files=all")
        self.assertNotIn("claims", status)

    def test_done_releases_a_fallback_claim(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        r = self.plan("done", "P-13", "--evidence", "tests pass")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Warning", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.fallback, "P-13.json")))

    def test_a_writable_git_folder_is_still_the_first_choice(self):
        os.chmod(self.primary, 0o700)
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.primary, "P-13.json")))
        self.assertFalse(os.path.exists(self.fallback))


class DoneTests(PlanBase):
    def test_done_with_evidence(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        r = self.plan("done", "P-13", "--evidence", "login tests pass (12 of 12)")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(self.get(PLAN_PATH), r"- \[x\] P-13 Add login · done means: login tests pass · evidence: login tests pass \(12 of 12\) \(\d{4}-\d\d-\d\dT\d\d:\d\dZ\)\n")
        self.assertEqual(self.get(PLAN_PATH).count("[x]"), 1)
        self.assertIn("- **State:** done\n", self.get("%s/P-13.md" % STATUS))
        self.assertFalse(self.has_claim("P-13"))
        self.assertEqual([e["payload"]["id"] for e in self.evs("task.done")], ["P-13"])
        self.assertIn("[done*]", self.plan("list").stdout)  # a person's evidence is believed, not proven
        self.assertEqual(self.plan("check").returncode, 0)

    def test_done_warns_when_the_claim_cannot_be_removed(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        claims = os.path.dirname(self.claim_path("P-13"))
        os.chmod(claims, 0o500)  # a read-only claims folder, as in a sandbox that protects .git
        try:
            r = self.plan("done", "P-13", "--evidence", "tests pass")
        finally:
            os.chmod(claims, 0o700)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Marked P-13 done.", r.stdout)
        self.assertIn("Warning: its claim is still in", r.stdout)
        self.assertIn("plan put-back P-13", r.stdout)

    def test_done_unverified(self):
        r = self.plan("done", "P-14", "--unverified")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(self.get(PLAN_PATH), r"evidence: checked by a person, not verified \(\d{4}-\d\d-\d\dT\d\d:\d\dZ\)\n")
        _r, data = self.jplan("list")
        self.assertIs({v["id"]: v for v in data["items"]}["P-14"]["verified"], False)

    def test_done_without_evidence_asks(self):
        q = self.question(self.plan("done", "P-13", "--json"))
        self.assertEqual((q["ask"], q["free_text"]), ("evidence", True))
        self.assertEqual(q["options"][0]["value"], "--unverified")
        self.assertEqual(self.get(PLAN_PATH), PLAN)
        self.assertEqual(self.plan("done", "P-99", "--unverified").returncode, 1)

    def test_done_twice_is_an_error_and_other_lines_are_untouched(self):
        self.assertEqual(self.plan("done", "P-13", "--evidence", "ok").returncode, 0)
        self.assertEqual(self.plan("done", "P-13", "--evidence", "ok").returncode, 1)
        lines = self.get(PLAN_PATH).split("\n")
        self.assertEqual(lines[:3] + lines[4:], PLAN.split("\n")[:3] + PLAN.split("\n")[4:])

    def test_crlf_plan_keeps_line_ends(self):
        crlf = PLAN.replace("\n", "\r\n")
        self.put(PLAN_PATH, crlf)
        self.assertEqual(self.plan("done", "P-14", "--evidence", "ok").returncode, 0)
        after = self.get(PLAN_PATH)
        self.assertEqual(after.count("\r\n"), after.count("\n"))
        self.assertIn("[x] P-14", after)

    def test_done_without_a_status_file_still_works(self):
        self.assertEqual(self.plan("done", "P-15", "--evidence", "ok").returncode, 0)
        self.assertFalse(self.has("%s/P-15.md" % STATUS))


STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\dZ"
JOURNAL = "%s/journal/P-13.md" % STATUS
PRINT_30 = "i=1; while [ $i -le 30 ]; do echo line$i; i=$((i+1)); done; echo oops >&2; exit 3"


class AtomicWriteTests(PlanBase):
    """P-29: PLAN.md and progress files are swapped in whole."""

    def leftovers(self, rel):
        folder = os.path.dirname(self.p(rel))
        return [n for n in os.listdir(folder) if n.endswith(".tmp")]

    def test_atomic_write_plan_and_progress_files_leave_no_temp_file(self):
        from wn import status
        self.assertTrue(plan.rewrite_item(self.p(PLAN_PATH), "P-13", lambda line: line.replace("[ ]", "[x]")))
        self.assertIn("- [x] P-13", self.get(PLAN_PATH))
        self.assertEqual(self.leftovers(PLAN_PATH), [])
        status.write_text(self.p(STATUS + "/P-13.md"), "# P-13: x\n", warn=False)
        self.assertEqual(self.get(STATUS + "/P-13.md"), "# P-13: x\n")
        self.assertEqual(self.leftovers(STATUS + "/P-13.md"), [])

    def test_atomic_write_a_failed_write_leaves_the_old_file_whole(self):
        from unittest import mock
        from wn import util
        before = self.get(PLAN_PATH)
        with mock.patch.object(util.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                plan.rewrite_item(self.p(PLAN_PATH), "P-13", lambda line: line.replace("[ ]", "[x]"))
        self.assertEqual(self.get(PLAN_PATH), before)
        self.assertEqual(self.leftovers(PLAN_PATH), [])
        with mock.patch.object(util.os, "fsync", side_effect=OSError("io error")):
            with self.assertRaises(OSError):
                util.write_atomic(self.p(PLAN_PATH), "half")
        self.assertEqual(self.get(PLAN_PATH), before)
        self.assertEqual(self.leftovers(PLAN_PATH), [])

    def test_atomic_write_keeps_a_symlink_the_mode_and_crlf(self):
        from wn import util
        real = self.p("docs/real-plan.md")
        os.makedirs(os.path.dirname(real), exist_ok=True)
        with open(real, "w", encoding="utf-8", newline="") as f:
            f.write("a\r\nb\r\n")
        os.chmod(real, 0o640)
        link = self.p("docs/link-plan.md")
        os.symlink(real, link)
        util.write_atomic(link, "x\r\ny\r\n")
        self.assertTrue(os.path.islink(link))
        with open(real, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), "x\r\ny\r\n")
        self.assertEqual(os.stat(real).st_mode & 0o777, 0o640)


class DriftTests(PlanBase):
    def started(self):
        r = self.start("P-13", "--branch", "stay")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def check(self):
        return self.plan("check").stdout

    def test_orphan_claim_a_deleted_item_leaves_a_claim_and_a_progress_file(self):
        self.started()
        self.assertNotIn("not in plan", self.check())
        self.put(PLAN_PATH, "\n".join(l for l in self.get(PLAN_PATH).split("\n") if "P-13" not in l))
        out = self.check()
        self.assertIn("warning: claim for P-13, not in plan", out)
        self.assertIn("warning: progress file for P-13, not in plan", out)

    def test_orphan_claim_a_hand_tick_still_claimed(self):
        self.started()
        self.put(PLAN_PATH, self.get(PLAN_PATH).replace("- [ ] P-13", "- [x] P-13"))
        self.assertIn("P-13 ticked by hand but still claimed", self.check())

    def test_orphan_claim_title_changed_since_start_and_the_note_reads_plan_live(self):
        self.started()
        self.put(PLAN_PATH, self.get(PLAN_PATH).replace("P-13 Add login", "P-13 Add single sign-on"))
        self.assertIn('P-13 title changed since start: plan says "Add single sign-on", progress file says "Add login"', self.check())
        note = self.gw(["progress", "resume-note"]).stdout
        self.assertIn("continue P-13 Add single sign-on", note)

    def test_orphan_claim_a_quiet_plan_has_no_drift_warning(self):
        self.started()
        out = self.check()
        self.assertNotIn("not in plan", out)
        self.assertNotIn("changed since start", out)
        self.assertNotIn("ticked by hand", out)


class DoneMeansCommandTests(PlanBase):
    def test_done_means_command_warns_on_an_open_item_without_a_backticked_command(self):
        self.put(PLAN_PATH, "# Plan\n\n## Now\n\n- [ ] P-1 A · done means: it works\n- [ ] P-2 B · done means: `python3 -m unittest` passes\n"
                            "- [x] P-3 C · done means: done already · evidence: verified: true passed in 1 s (t)\n- [ ] P-4 D\n")
        out = self.plan("check").stdout
        self.assertIn("warning: P-1: done means has no command in backticks, so `plan done P-1 --verify` has nothing to run.", out)
        self.assertNotIn("P-2:", out)  # has a command
        self.assertNotIn("P-3:", out)  # already done
        self.assertIn('P-4 has no "done means".', out)  # the older warning stays, with no second one for P-4
        self.assertNotIn("P-4: done means", out)
        self.assertEqual(self.plan("check").returncode, 0)  # a warning, never an error

    def test_done_means_command_empty_backticks_do_not_count(self):
        self.put(PLAN_PATH, "# Plan\n\n## Now\n\n- [ ] P-1 A · done means: run `` and see\n")
        self.assertIn("P-1: done means has no command in backticks", self.plan("check").stdout)


class SuggestFieldTests(PlanBase):
    PLAN = """# Plan

## Now

- [ ] P-1 After done means · done means: a · suggest: sonnet/high
- [ ] P-2 Before done means · suggest: haiku/low · done means: b
- [ ] P-3 No hint · done means: c
- [ ] P-4 Odd value · done means: d · suggest:   opus \x1b[31m/  max
"""

    def setUp(self):
        super().setUp()
        self.put(PLAN_PATH, self.PLAN)
        self.commit("suggest plan")

    def test_suggest_field_is_kept_as_written_before_or_after_done_means(self):
        _lines, items = plan.parse_text(self.PLAN)
        by_id = {i.id: i for i in items}
        self.assertEqual(by_id["P-1"].suggest, "sonnet/high")
        self.assertEqual(by_id["P-2"].suggest, "haiku/low")
        self.assertEqual(by_id["P-3"].suggest, "")
        self.assertEqual((by_id["P-1"].done_means, by_id["P-2"].done_means), ("a", "b"))
        self.assertEqual((by_id["P-1"].title, by_id["P-2"].title), ("After done means", "Before done means"))
        self.assertEqual(by_id["P-4"].suggest, "opus [31m/ max".replace("\x1b", ""))  # tidied, never executed

    def test_suggest_field_shows_in_next_list_and_start(self):
        r, data = self.jplan("next", "--limit", "10")
        self.assertEqual({c["id"]: c["suggest"] for c in data["candidates"]},
                         {"P-1": "sonnet/high", "P-2": "haiku/low", "P-3": "", "P-4": "opus [31m/ max"})
        r, data = self.jplan("list")
        self.assertIn('"suggest": "sonnet/high"', self.plan("list", "--json").stdout)
        r, started = self.jplan("start", "P-1", "--branch", "stay")
        self.assertEqual(started["suggest"], "sonnet/high")
        out = self.plan("start", "P-2", "--branch", "stay", "--current", "keep").stdout
        self.assertIn("Suggest: haiku/low", out)

    def test_suggest_field_a_line_without_it_is_unchanged(self):
        out = self.plan("start", "P-3", "--branch", "stay").stdout
        self.assertNotIn("Suggest:", out)
        self.assertIn("Done means: c", out)
        self.assertEqual(self.get(PLAN_PATH), self.PLAN)  # reading never rewrites the plan


class BlockedByTests(PlanBase):
    PLAN = """# Plan

## Now

- [ ] P-1 First job · done means: a
- [ ] P-2 Second job · done means: b · blocked by: P-1
- [ ] P-3 Third job · blocked by: P-1, P-2 · done means: c
- [ ] P-4 Free job · done means: d

## Next

- [ ] P-5 Later job · done means: e · blocked by: P-9
"""

    def setUp(self):
        super().setUp()
        self.put(PLAN_PATH, self.PLAN)
        self.commit("blocked plan")

    def ids(self):
        r, data = self.jplan("next", "--limit", "10")
        return [c["id"] for c in data["candidates"]]

    def test_blocked_by_parses_in_either_position(self):
        _lines, items = plan.parse_text(self.PLAN)
        by_id = {i.id: i for i in items}
        self.assertEqual(by_id["P-1"].blocked_by, [])
        self.assertEqual(by_id["P-2"].blocked_by, ["P-1"])
        self.assertEqual(by_id["P-3"].blocked_by, ["P-1", "P-2"])
        self.assertEqual(by_id["P-3"].done_means, "c")  # the field does not leak into done means
        self.assertEqual(by_id["P-2"].title, "Second job")

    def test_blocked_by_next_skips_an_item_whose_blocker_is_open(self):
        self.assertEqual(self.ids(), ["P-1", "P-4"])  # P-2 and P-3 wait; P-5 is in Next and Now has candidates
        r = self.plan("done", "P-1", "--unverified")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ids(), ["P-2", "P-4"])  # P-3 still waits for P-2
        self.plan("done", "P-2", "--unverified")
        self.assertEqual(self.ids(), ["P-3", "P-4"])

    def test_blocked_by_says_so_when_everything_waits_and_list_json_has_the_fields(self):
        self.put(PLAN_PATH, "# Plan\n\n## Now\n\n- [ ] P-1 A · blocked by: P-2\n- [ ] P-2 B · blocked by: P-1\n")
        r = self.plan("next")
        self.assertIn("Nothing ready in Now or Next: P-1, P-2 wait for open items", r.stdout)
        self.assertIn('"blocked_on"', self.plan("list", "--json").stdout)

    def test_blocked_by_check_reports_an_id_that_is_not_in_the_plan(self):
        out = self.plan("check").stdout
        self.assertIn("warning: P-5 is blocked by P-9, which is not in the plan.", out)
        self.assertNotIn("P-2 is blocked by", out)
        self.put(PLAN_PATH, self.PLAN.replace("blocked by: P-1\n", "blocked by: P-2\n"))
        self.assertIn("P-2 is blocked by itself.", self.plan("check").stdout)


class FileOverlapTests(PlanBase):
    def setUp(self):
        super().setUp()
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-16 Audit log", "- [ ] P-16 Audit log · done means: it logs"))
        self.commit("plan")

    def test_file_overlap_start_warns_when_another_in_progress_item_lists_the_same_files(self):
        self.assertEqual(self.start("P-13", "--branch", "stay").returncode, 0)
        self.task("P-13", branch=self.branch(), files="src/a.py, src/b.py")
        self.put("%s/P-16.md" % STATUS, task_text("P-16", title="Audit log", state="parked", branch=self.branch(),
                                                  files="src/b.py, src/c.py"))
        r = self.plan("start", "P-16", "--agent", "codex", "--branch", "stay", "--current", "keep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("warning: P-16 lists files that P-13 (in progress) also lists: src/b.py.", r.stderr)
        self.assertIn("Started P-16", r.stdout)  # advice only: the start still happens

    def test_file_overlap_json_and_the_resume_note(self):
        self.start("P-13", "--branch", "stay")
        self.task("P-13", branch=self.branch(), files="src/a.py")
        self.put("%s/P-16.md" % STATUS, task_text("P-16", title="Audit log", state="parked", branch=self.branch(), files="src/a.py"))
        r, data = self.jplan("start", "P-16", "--agent", "codex", "--branch", "stay", "--current", "keep")
        self.assertEqual(data["file_overlap"], [{"id": "P-13", "files": ["src/a.py"]}])
        note = self.gw(["progress", "resume-note"]).stdout
        self.assertIn("Overlap: P-16 lists files that P-13 (in progress) also lists: src/a.py.", note)

    def test_file_overlap_no_shared_file_no_warning(self):
        self.start("P-13", "--branch", "stay")
        self.task("P-13", branch=self.branch(), files="src/a.py")
        self.put("%s/P-16.md" % STATUS, task_text("P-16", title="Audit log", state="parked", branch=self.branch(), files="src/z.py"))
        r = self.plan("start", "P-16", "--agent", "codex", "--branch", "stay", "--current", "keep")
        self.assertNotIn("also lists", r.stderr)


class OutputTailTests(unittest.TestCase):
    def test_tail_strips_colors_blank_ends_and_clips(self):
        self.assertEqual(plan.output_tail(b"a\n\x1b[31mred\x1b[0m\n\n"), ["a", "red"])
        self.assertEqual(plan.output_tail("\n".join("l%d" % n for n in range(50))), ["l%d" % n for n in range(30, 50)])
        self.assertEqual(len(plan.output_tail("x" * 500)[0]), plan.VERIFY_LINE_MAX)
        self.assertEqual(plan.output_tail(b""), [])


class VerifyTests(PlanBase):
    """`plan done <id> --verify "<cmd>"` (ADR-0003)."""

    def test_pipe_warning(self):
        self.assertTrue(plan.pipe_without_pipefail("python3 -m unittest 2>&1 | tail -3"))
        self.assertTrue(plan.pipe_without_pipefail("make test | head"))
        self.assertFalse(plan.pipe_without_pipefail("set -o pipefail; make test | tail"))
        self.assertFalse(plan.pipe_without_pipefail("make test"))
        self.assertFalse(plan.pipe_without_pipefail("a || b"))
        self.assertFalse(plan.pipe_without_pipefail("grep 'a|b' file"))
        self.assertFalse(plan.pipe_without_pipefail('echo "x | y"'))
        self.assertFalse(plan.pipe_without_pipefail(""))
        r = self.plan("done", "P-13", "--verify", "true | cat")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # a warning, not a refusal
        self.assertIn("has a pipe and no `pipefail`", r.stderr)
        r = self.plan("done", "P-16", "--verify", "test -f README.md")
        self.assertNotIn("pipefail", r.stderr)

    def test_verify_records_state(self):
        r = self.plan("done", "P-13", "--verify", "test -f README.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        head = self.head()
        self.assertRegex(self.get(PLAN_PATH), r"\(%s\) at %s t:[0-9a-f]{8}\n" % (STAMP, head))
        self.assertNotIn("changed since", self.plan("check").stdout)  # right after verify: nothing changed
        self.commit("record the verify")  # PLAN.md and progress files only: still the same code
        self.assertNotIn("changed since", self.plan("check").stdout)
        self.put("src/new.py", "x = 1\n")  # an edit
        out = self.plan("check").stdout
        self.assertIn("warning: P-13 was verified at %s, and the code has changed since. Run its verify again." % head, out)
        self.commit("feat: new")
        out = self.plan("check").stdout
        self.assertIn("verified at %s, and the code has changed since (1 commit)." % head, out)
        self.assertIn("verified_stale", self.plan("list", "--json").stdout)

    def test_evidence_without_a_state_is_never_flagged(self):
        self.put(PLAN_PATH, PLAN.replace("- [ ] P-16 Audit log", "- [x] P-16 Audit log · done means: x · evidence: verified: true passed in 1 s (t)"))
        self.put("src/new.py", "x = 1\n")
        self.assertNotIn("changed since", self.plan("check").stdout)

    def test_pass_ticks_the_item_with_verified_evidence_and_list_shows_plain_done(self):
        r = self.plan("done", "P-13", "--verify", "test -f README.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(self.get(PLAN_PATH),
                         r"- \[x\] P-13 Add login · done means: login tests pass · evidence: verified: test -f README.md passed in \d+(\.\d)? s \(%s\)( at [0-9a-f]{7,} t:[0-9a-f]{8})?\n" % STAMP)
        self.assertEqual(self.get(PLAN_PATH).count("[x]"), 1)
        out = self.plan("list").stdout
        self.assertIn("P-13  Add login  [done]", out)
        self.assertNotIn("done*", out)
        self.assertNotIn("not verified", out)
        _r, data = self.jplan("list")
        self.assertIs({v["id"]: v for v in data["items"]}["P-13"]["verified"], True)
        self.assertEqual(self.plan("check").returncode, 0)
        self.assertEqual([e["payload"]["id"] for e in self.evs("task.done")], ["P-13"])
        self.assertFalse(self.has(JOURNAL))  # a pass writes no journal line

    def test_pass_sets_the_progress_note_to_confirmed(self):
        self.task("P-13", note="auto (3 turns since wrap-up, 2026-11-04T20:10Z)")
        r = self.plan("done", "P-13", "--verify", "true")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = self.get("%s/P-13.md" % STATUS)
        self.assertRegex(text, r"- \*\*Note:\*\* confirmed \(%s\)\n" % STAMP)
        self.assertNotIn("auto (", text)
        self.assertIn("- **State:** done\n", text)
        # the same minute is in the evidence and the Note
        stamps = set(__import__("re").findall(r"\((%s)\)" % STAMP, self.get(PLAN_PATH) + text))
        self.assertEqual(len(stamps), 1)

    def test_pass_without_a_progress_file_creates_none(self):
        self.assertEqual(self.plan("done", "P-15", "--verify", "true").returncode, 0)
        self.assertFalse(self.has("%s/P-15.md" % STATUS))

    def test_pass_json(self):
        r, data = self.jplan("done", "P-13", "--verify", "true")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIs(data["done"], True)
        self.assertEqual((data["id"], data["verify"]["command"], data["verify"]["passed"], data["verify"]["exit_code"]),
                         ("P-13", "true", True, 0))
        self.assertIs(data["verify"]["timed_out"], False)
        self.assertIn("Marked P-13 done", data["message"])

    def test_fail_leaves_the_plan_alone_and_journals_the_last_20_lines(self):
        self.task("P-13", note="auto (2 turns, 2026-11-04T20:10Z)")
        before_progress = self.get("%s/P-13.md" % STATUS)
        self.put(JOURNAL, "# Journal: P-13\n\n- 2026-11-04T21:58Z stop 5367d1d main dirty=0\n")
        r = self.plan("done", "P-13", "--verify", PRINT_30)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("exit 3", r.stderr)
        self.assertIn("P-13 stays open", r.stderr)
        self.assertIn("oops", r.stderr)
        self.assertEqual(self.get(PLAN_PATH), PLAN)
        self.assertEqual(self.get("%s/P-13.md" % STATUS), before_progress)
        text = self.get(JOURNAL)
        self.assertTrue(text.startswith("# Journal: P-13\n\n- 2026-11-04T21:58Z stop 5367d1d main dirty=0\n"))
        self.assertRegex(text, r"- %s verify failed \(exit 3, \d+(\.\d)? s\): i=1; while \[ \$i" % STAMP)
        tail = [l for l in text.splitlines() if l.startswith("    ")]
        self.assertEqual(len(tail), 20)
        self.assertEqual(tail[0], "    line12")
        self.assertEqual(tail[-1], "    oops")  # stderr is captured with stdout
        self.assertNotIn("line11\n", text)
        self.assertEqual(journal.last_commit(self.p(JOURNAL)), "5367d1d")  # the facts layer's base is unchanged
        self.assertEqual(self.evs("task.done"), [])

    def test_fail_json_prints_the_result_and_exits_non_zero(self):
        r, data = self.jplan("done", "P-13", "--verify", "echo nope; exit 2")
        self.assertEqual(r.returncode, 1)
        self.assertIs(data["done"], False)
        self.assertEqual((data["verify"]["passed"], data["verify"]["exit_code"], data["verify"]["output_tail"]),
                         (False, 2, ["nope"]))
        self.assertEqual(data["verify"]["journal"], JOURNAL)
        self.assertEqual(self.get(PLAN_PATH), PLAN)

    def test_fail_with_no_output_and_unknown_command(self):
        r = self.plan("done", "P-13", "--verify", "false")
        self.assertEqual(r.returncode, 1)
        self.assertIn("(no output)", self.get(JOURNAL))
        r = self.plan("done", "P-13", "--verify", "no-such-command-xyz-123")
        self.assertEqual(r.returncode, 1)
        self.assertIn("exit 127", self.get(JOURNAL))
        self.assertEqual(self.get(PLAN_PATH), PLAN)

    def test_timeout_counts_as_a_failure(self):
        self.cfg(plan={"verifyTimeout": "1s"})
        started = datetime.datetime.now()
        r = self.plan("done", "P-13", "--verify", "echo started; sleep 30")
        self.assertLess((datetime.datetime.now() - started).total_seconds(), 20)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("timed out after 1.0 s", r.stderr)
        self.assertEqual(self.get(PLAN_PATH), PLAN)
        self.assertIn("verify failed (timed out after 1.0 s", self.get(JOURNAL))
        self.assertIn("    started", self.get(JOURNAL))

    def test_evidence_still_marks_done_star(self):
        self.task("P-13", note="auto (2 turns, 2026-11-04T20:10Z)")
        self.assertEqual(self.plan("done", "P-13", "--evidence", "I read the diff").returncode, 0)
        out = self.plan("list").stdout
        self.assertIn("P-13  Add login  [done*]", out)
        self.assertIn("* checked by a person, not verified", out)
        self.assertNotIn("verified:", self.get(PLAN_PATH))
        self.assertIn("- **Note:** auto (", self.get("%s/P-13.md" % STATUS))  # a person's word does not confirm the note

    def test_verify_with_evidence_or_unverified_is_rejected_and_nothing_runs(self):
        for flag in (["--evidence", "ok"], ["--unverified"]):
            r = self.plan("done", "P-13", "--verify", "touch ran.flag", *flag)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("--verify cannot be combined with --evidence or --unverified", r.stderr)
            self.assertEqual(self.get(PLAN_PATH), PLAN)
            self.assertFalse(self.has("ran.flag"))
        r = self.plan("done", "P-13", "--verify", "   ")
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs a command", r.stderr)

    def test_unknown_or_done_items_do_not_run_the_command(self):
        self.assertEqual(self.plan("done", "P-99", "--verify", "touch ran.flag").returncode, 1)
        self.assertEqual(self.plan("done", "P-13", "--evidence", "ok").returncode, 0)
        r = self.plan("done", "P-13", "--verify", "touch ran.flag")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already done", r.stderr)
        self.assertFalse(self.has("ran.flag"))

    def test_the_command_comes_only_from_the_command_line(self):
        self.put(PLAN_PATH, PLAN.replace("login tests pass", "login tests pass · verify: touch plan.flag"))
        self.put("%s/P-13.md" % STATUS, task_text("P-13", next_action="Run: touch progress.flag"))
        self.assertEqual(self.plan("done", "P-13", "--verify", "true").returncode, 0)
        self.assertFalse(self.has("plan.flag"))
        self.assertFalse(self.has("progress.flag"))

    def test_runs_from_the_project_root_even_when_started_in_a_subfolder(self):
        sub = os.path.join(self.proj, "docs")
        os.makedirs(sub, exist_ok=True)
        r = self.plan("done", "P-13", "--verify", "test -f README.md && touch ran-here.flag", cwd=sub)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.has("ran-here.flag"))

    def test_the_separator_and_line_breaks_in_a_command_do_not_break_the_plan_line(self):
        r = self.plan("done", "P-13", "--verify", "echo a · b\ntrue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = [l for l in self.get(PLAN_PATH).split("\n") if "P-13" in l][0]
        self.assertIn("evidence: verified: echo a - b true passed in", line)
        _r, data = self.jplan("list")
        self.assertIs({v["id"]: v for v in data["items"]}["P-13"]["verified"], True)


if __name__ == "__main__":
    unittest.main()
