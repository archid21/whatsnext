# ADR-0019: Claude Code wrap-up ends without a /compact template, and a recent unrelated handoff steers a new session

- **Date:** 2026-11-09T18:30Z
- **Status:** accepted (user), 2026-11-09

Builds on ADR-0008 and ADR-0009 (point 1, for Claude Code).

## Decision

1. **Claude Code wrap-up ending:** the agent ends its reply with two lines: `Handoff written: <path>`, then one line that says to run `/compact` (the handoff is added to the compact) or `/clear` for a fresh start. The reply no longer carries the `/compact <text>` template. Codex keeps the three-line ending with the template.
2. **Recent handoff at session start:** with no active task, a handoff note with `Task: none` that was written in the last 24 hours (`RECENT_HANDOFF_HOURS`) puts its Goal and Next action in the SessionStart note, as `Goal (handoff <UTC>): ...` and `Next (handoff <UTC>): ...`. An older note, or a note for a task id, is only pointed to, as before.

## Why

1. The PreCompact hook already carries the handoff facts into every Claude Code compact (auto, idle or a plain `/compact`). The printed `/compact` line repeated that work and read as an instruction to paste text. Codex ignores PreCompact text, so Codex still needs the line.
2. After `wrap up` and `/clear`, a new window has no active task. Its note said only "another session's note" and gave no next step. The Goal and Next action of a recent `Task: none` note are the next step the user just wrote down.

## Trade-offs and risks

- An unrelated recent note can steer a new window. The label names the handoff time, so the agent and the user can see how old it is. The 24-hour limit keeps old notes out.
- The Claude Code reply has one `/compact` hint, not a paste-ready template. A user who wants the template runs `compact-instructions`.
