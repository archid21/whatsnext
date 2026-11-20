# ADR-0032: Fan out ready items: one separate session per item in its own worktree, capped by `plan.fanOutCap`

- **Date:** 2026-11-20T18:06Z
- **Status:** accepted (user), 2026-11-20

Builds on ADR-0020 (session-aware claims, worktrees) and ADR-0017 (one execution contract for Codex and Claude Code).

## Context

P-63 asks for one worker per ready item, each with its own claim. "Run ready items in parallel" today means one agent works the approved items one after another (SKILL.md). Two ways to run workers side by side:

- **Subagents** (Claude Code Agent tool, Codex sub-agents) share their parent's session id (ADR-0020). Their claims cannot be told apart from the parent's, and they edit one working tree, so commits and test runs mix.
- **Separate sessions**, each with its own session id, can hold their own claim and work in their own worktree.

The Claude desktop app limits session proposals per turn to about 4.

## Decision

1. **A worker is one separate session per item, in its own worktree.** Not a subagent.
2. **A cap on how many start at once: the setting `plan.fanOutCap`.** Integer, default 4, minimum 1. An invalid value falls back to 4 and is reported like any other setting error. Ready items past the cap stay in the queue for the next fan-out. The default matches the desktop app's limit of about 4 session proposals per turn.
3. **The parent claims each item before it starts that item's worker.** A failed claim (another agent or session holds it) skips that item; the others go on. The parent says which items it skipped.
4. **Each worker ends on its own branch.** Merging stays with the user. Nothing is pushed.
5. **Codex, which cannot start sessions, falls back to a numbered list of commands** the user runs, one per item (open the worktree folder, start the agent there, `plan start <id>`).

## Why

- Separate sessions keep claims distinguishable (ADR-0020 rule 1) and keep files, commits and test runs apart.
- A cap bounds token cost and review load, and a user with a different tolerance can change it.
- Claiming in the parent first means a worker never starts on an item someone else holds.
- Leaving merges and pushes to the user matches the local-only rule.

## Trade-offs and risks

- A worktree starts from the last commit, so uncommitted work is not in it. Items that depend on it need `blocked by:` (ADR-0014).
- Worktrees need cleanup after merge.
- Each worker is a full session, so token cost grows with the number of items. The cap limits it; it does not remove it.
- Parallel items can touch the same files; the file-overlap warning (P-11) shows at start, and merges may conflict.
- The cap value above 4 may exceed what the desktop app accepts in one turn; the parent would then propose in batches or fall back to the numbered list.
