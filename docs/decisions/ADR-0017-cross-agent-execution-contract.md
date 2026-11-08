# ADR-0017: One execution contract for Codex and Claude Code

- **Date:** 2026-11-08T17:15Z
- **Status:** accepted (user), 2026-11-08, instruction to fix the reviewed continuity and execution gaps

The shared plan, progress and handoff files remain the source of truth. Both agents handle `wrap up`; small conversation readers normalize known message formats for freshness and latest-request carryover. This extends ADR-0015 to Codex without relying on its ignored PreCompact output. Unknown conversation formats remain unverified. Keeping one workflow avoids duplicating state transitions, at the cost of maintaining fixtures as agent formats change.

`plan next` recommends current checkout work before ready new work and flags handoffs referencing completed tasks. The skill reports milestones and persists the same status for the next chat. One-task execution remains the default; explicit whole-plan approval applies only to the displayed item IDs and checks.

`plan done --verify` runs the backticked completion command when done means has exactly one; with several, `--verify CMD` picks one. A command that matches any backticked part (exact text, including whitespace) needs no override. Any other command requires an explicit user-approved override reason stored in the evidence. (Amended 2026-11-08: the first version accepted only a single backticked part and compared exact text, which rejected valid commands.) This tightens ADR-0003: a successful arbitrary command is no longer silently substituted for the saved check. Command success proves that check, not additional manual acceptance criteria.

Codex installation covers fork startup, session end and interruption. Health reports distinguish configuration from per-agent runtime observations; observations do not certify a live end-to-end handoff. The checkout installer remains supported. Native Codex plugin packaging is a separate distribution choice, not required for these fixes.

Amended 2026-11-08 following verification review: preserve shell-significant whitespace and compare exact command text, including quotes and newlines. The user approved this correction. Multiple backticked choices remain supported; any different text requires an approved override.
