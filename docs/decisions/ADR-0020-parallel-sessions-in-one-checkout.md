# ADR-0020: Parallel sessions in one checkout: session-aware claims, a worktree by default, and an "always" offer after two equal answers

- **Date:** 2026-11-09T20:11Z
- **Status:** accepted (user), 2026-11-09

Builds on ADR-0002 (branch question at Start) and ADR-0017 (one execution contract for Codex and Claude Code).

## Context

One session works on P-3. The user opens a second chat in the same folder and says "Work on P-4". Today:

- `claims.is_ours` compares only the agent name and the worktree, so a second Claude Code session in the same folder counts as the owner of the first session's claim.
- `status.active_task` picks by branch, then by the latest Updated. After P-4 starts, both sessions resolve to P-4, and the first session's hooks write to P-4's progress file.
- Both sessions edit one working tree, so commits and test runs mix the two items.

Subagents (Claude Code Agent tool, Codex sub-agents) share their parent's session id and are not affected.

## Decision

1. **A claim belongs to a session.** `is_ours` also requires the same session id when both claims have one. A claim held by another session in the same worktree, updated within `staleAfter`, is a conflict, not a re-run. A claim without a session id keeps today's rule.
2. **The active task is chosen per session.** `active_task` and `branch_task` prefer the active item claimed by this session, then fall back to today's branch rule. Hooks that write only touch this session's item.
3. **Start asks when another session is live in this checkout.** The question: "P-3 is in progress in another session here. Where should P-4 go?" with **New worktree (recommended)** and **Stay on this branch**. A new worktree uses the existing `--branch worktree` path, and Start prints the folder to open.
4. **A separate setting, `concurrentStart: ask | worktree | stay`** (default `ask`). The existing `branch` setting does not decide this case.
5. **The "always" offer comes after two equal answers in a row.** Then a non-blocking band in Claude Code: "Always use a new worktree when another session is working here? [Always] [Keep asking]". Ignoring it means keep asking. In Codex, the offer is one line at the end of the reply and the user answers in chat (`--always`).
6. **The band only offers "always worktree".** `stay` is set only by editing the config or by an explicit request in chat.
7. **Staying on the branch shows a warning** at Start: "P-3 is in progress in another session in this folder. Edits and commits will mix."

## Why

- A worktree is the only option that keeps files, commits and test runs apart; git already does the work.
- Session-aware claims and active-task selection make the shared-folder case correct when the user stays anyway.
- One question per Start; the offer after two equal answers shows a real pattern and avoids a second prompt for one decision.
- A separate setting keeps a safe solo default (`branch: stay`) from deciding the risky shared case.

## Trade-offs and risks

- A new worktree starts from the last commit, so uncommitted P-3 work is not in it. If P-4 depends on P-3, `blocked-by` (ADR-0014) should hold P-4 back.
- The user must open the new folder in the second chat. Worktrees need cleanup after merge.
- A crashed session leaves a live-looking claim until `staleAfter` passes; the stale-claim question (ADR-0002) still applies.
- Two answer counters per project add a small state file; it follows ADR-0018 pruning.
