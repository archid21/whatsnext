# Plan

One line per item: `- [ ] P-N Title · done means: <how we know it is done>`.

## Now

- [x] P-4 Auto-compact safety net (with P-20, P-26) · done means: `python3 -m unittest tests.test_hook -k compacted_without_wrapup` passes and the resume note shows the same fact · evidence: verified: python3 -m unittest tests.test_hook -k compacted_without_wrapup passed in 1.4 s (2026-11-06T18:20Z)
- [x] P-20 Cap the PreCompact text and read `custom_instructions` (part of P-4 bundle) · done means: `precompact_cap` test passes: output is 3,000 characters or less, and a non-empty `custom_instructions` drops the handoff text · evidence: verified: python3 -m unittest tests.test_hook -k precompact_cap passed in 1.0 s (2026-11-06T18:20Z)
- [x] P-26 Hook output contract test (part of P-4 bundle) · done means: `python3 -m unittest tests.test_hook -k output_contract` passes: PreCompact prints plain text, never JSON · evidence: verified: python3 -m unittest tests.test_hook -k output_contract passed in 2.4 s (2026-11-06T18:20Z)
- [x] P-6 Keep the latest request verbatim · done means: `python3 -m unittest tests.test_hook -k latest_request` passes: last real user prompt is printed, clipped to 2,000 characters, with tool results and `isMeta` entries skipped · evidence: verified: python3 -m unittest tests.test_hook -k latest_request passed in 2.2 s (2026-11-06T18:44Z)
- [x] P-5 Facts-only compact text when no handoff · done means: `python3 -m unittest tests.test_compact -k facts_only` passes: output lists task, branch, Next, plan step and files changed, with no newline · evidence: verified: python3 -m unittest tests.test_compact -k facts_only passed in 1.5 s (2026-11-06T19:02Z)
- [ ] P-8 Verify records the code state · done means: `python3 -m unittest tests.test_plan -k verify_records_state` passes and `plan check` flags a verified item after a new commit
- [ ] P-24 "Dead ends" line in the note and the compact text · done means: `python3 -m unittest tests.test_packet -k dead_ends` passes and the compact text keeps dead ends within 300 characters

## Next

- [ ] P-21 Keep the compact summary and check it · done means: `python3 -m unittest tests.test_hook -k postcompact_bak` passes: the previous summary is kept as `.bak` and the resume note shows the kept-steps line
- [ ] P-22 Codex marker fallback after compact · done means: `python3 -m unittest tests.test_hook -k compact_marker_once` passes: the resume note prints once at the next prompt, then the marker is gone
- [ ] P-25 Open subagents and in-progress todo in the keep-list · done means: `python3 -m unittest tests.test_compact -k subagents` passes: launched agents and the in-progress todo appear in the PreCompact text
- [ ] P-18 `whatsnext doctor` · done means: `python3 -m unittest tests.test_doctor` passes: each hook gap prints a fix line and a per-agent status line
- [ ] P-3 Wrap-up status in the note · done means: `python3 -m unittest tests.test_packet -k wrapup_status` passes: the note reads "wrapped up <UTC>" or "no handoff, facts only"
- [ ] P-14 Archive the handoff before overwrite · done means: `python3 -m unittest tests.test_wrapup -k archive` passes: the old note is saved under `docs/project/handoffs/` and only the last N are kept
- [ ] P-16 "Cut" line for the 1,200-character cap · done means: `python3 -m unittest tests.test_packet -k cut_line` passes: a trimmed note ends with "cut: Done +N, M commits. Full: progress show"
- [ ] P-17 Commit-based stale rule, set in config · done means: `python3 -m unittest tests.test_packet -k stale_commits` passes: N new commits make a note stale, and both limits are read from config
- [ ] P-15 Handoff-versus-git cross-check · done means: `python3 -m unittest tests.test_wrapup -k cross_check` passes: "named, not changed in git" and "changed, not named" appear in the sidecar and the note
- [ ] P-23 Handoff done-when check · done means: `python3 -m unittest tests.test_handoff_verify` passes: a git-tracked note refuses to run without the flag, and exit 0 archives the note
- [ ] P-1 Dirty-set digest · done means: `python3 -m unittest tests.test_journal -k digest` passes: same dirty count but a changed file set reads as "set changed"
- [ ] P-2 Ancestor check · done means: `python3 -m unittest tests.test_packet -k ancestor` passes: a commit that is not an ancestor of HEAD prints the stale warning and no "N new commits" line

## Later

- [ ] P-9 Verify pipe warning · done means: `python3 -m unittest tests.test_plan -k pipe_warning` passes: `plan done --verify` on a piped command with no `pipefail` prints a warning
- [ ] P-19 Codex plan-capture health · done means: `python3 -m unittest tests.test_hook -k capture_unreadable` passes: an unreadable Codex plan writes one `capture.unreadable` fact that `doctor` shows
- [ ] P-27 Orphan and drift check for claims and progress files · done means: `python3 -m unittest tests.test_plan -k orphan_claim` passes: deleting a claimed item makes `plan check` report "claim for P-N, not in plan"
- [ ] P-7 PLAN.md hand-tick guard · done means: `python3 -m unittest tests.test_hook -k plan_tick_guard` passes: a PreToolUse edit that ticks `- [ ] P-N` gets the "use `plan done --verify`" message
- [ ] P-11 File-overlap warning at `plan start` · done means: `python3 -m unittest tests.test_plan -k file_overlap` passes: starting an item whose Files list overlaps an in-progress item prints a warning
- [ ] P-10 Sibling-worktree claim view · done means: `python3 -m unittest tests.test_claims -k sibling_worktree` passes: a claim in another worktree's `.whatsnext/claims/` shows in `plan list`
- [ ] P-12 Two-agent soak test · done means: `python3 tests/soak_two_agents.py --runs 20` reports zero double claims across two worktrees
- [ ] P-13 `blocked by:` ready queue · done means: `python3 -m unittest tests.test_plan -k blocked_by` passes: `plan next` skips an item whose `blocked by:` item is still open
