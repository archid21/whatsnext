# Handoff

Session: 2230ec21-bc6b-4bd4-bf6a-f2c0f1c09e23
Task: none
Written: 2026-11-06T22:56Z

## Goal

Ship the next whatsnext release: the compact safety net, handoff checks and multi-agent fixes. All 31 plan items are built.

## Next action

Try the three unverified hooks in a real session (PreToolUse tick warning, PostCompact order, Codex hooks). Run `python3 skills/whatsnext/scripts/whatsnext.py doctor`.
Verify: `python3 -m unittest discover -s tests` passes (408 tests) and `doctor` shows no Claude Code gap.

## State

State on Fri 2026-11-06 2:56 PM PST (Pacific): all 31 plan items are done and verified. Branch p-4-auto-compact-safety-net-with-p-20-p-26 is merged into local main (1285a38, 39 commits ahead of origin/main, not pushed). PR #1 is open. Last full suite: 408 tests pass. Soak test: 0 double claims in 60 runs.

## What changed

- Compact: PreCompact and PostCompact hooks, latest request, facts line, dead ends, subagents, Codex once-only note (wn/hook.py, wn/compact.py, wn/wrapup.py)
- Handoff: archive, git cross-check, cut line, stale commits, `handoff verify` (wn/wrapup.py, wn/crosscheck.py, wn/handoffverify.py)
- Plan: verify records state, tick guard, drift checks, atomic writes, `suggest:`, `blocked by:` (wn/plan.py, wn/util.py)
- Health and claims: `doctor`, sibling-worktree claims, soak test (wn/doctor.py, wn/claims.py, tests/soak_two_agents.py)
- Tests 408, ADRs 0011 to 0014 in docs/decisions/

## Decisions

ADR-0011 PreCompact reads the transcript tail; ADR-0012 `suggest:` hint; ADR-0013 Dead ends section; ADR-0014 `blocked by:`. All accepted 2026-11-06, in docs/decisions/.

## Constraints

Standard library only, Python 3.9+. Do not push main or create a remote without asking (AGENTS.md); the user allowed the PR and the local merge only. Keep AGENTS.md under 30 lines. Run `python3 -m unittest discover -s tests` before reporting done. Never copy code from other tools. Run a suite with its exit code checked, not through a pipe.

## Open questions and blockers

Push main or merge PR #1 on GitHub? Not run in a real agent: Codex PreToolUse and UserPromptSubmit hooks, Codex PostCompact, the PreToolUse warning on Claude Code. `plan check` is noisy with stale-verify warnings.
