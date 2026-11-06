# ADR-0011: PreCompact reads the end of the transcript to keep the user's latest request

- **Date:** 2026-11-06T18:41Z
- **Status:** proposed (agent), awaiting the user's decision

Amends ADR-0005 item 3 ("no transcript reading") for one event.

## Decision

1. **PreCompact on Claude Code reads the last 1,000,000 bytes of the session transcript** (`transcript_path`) and takes the user's latest real request: not a tool result, not `isMeta`, sidechain or compact-summary, not a slash command or injected block, not `wrap up`.
2. **It prints that request under "Keep verbatim (the user's latest request):"**, redacted (private spans removed, secret-looking text replaced by `[redacted]`) and clipped to 2,000 characters. It counts toward the 3,000-character PreCompact cap (P-20); the handoff text is cut first.
3. **Nothing is stored on disk.** No model call. A missing or unreadable transcript prints no block and never fails the hook.
4. **Other events do not read the transcript.** Codex PreCompact output is ignored, so Codex is unchanged.

## Why

A summary loses parts of a long request, and the request is what the next turn must act on. Reading the transcript tail at the moment of the compact keeps it without storing prompts.

## Cost

Claude Code's transcript format has no stability promise. A change makes the block disappear; the rest of the hook still works.
