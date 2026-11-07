# ADR-0015: The resume note after a compact repeats the user's latest request and the open work

- **Date:** 2026-11-07T06:20Z
- **Status:** proposed (agent suggestion; the user asked for the change, has not yet accepted this record)

Amends ADR-0011 item 3 ("nothing is stored on disk") for the text below.

## Decision

1. **PreCompact on Claude Code saves a short carry text** in the git-ignored `.whatsnext/sessions/<session>.compact.json` (field `carry`): the user's latest request (redacted, at most 250 characters) and the subagent and in-progress todo line (at most 150 characters). About 420 characters in all.
2. **The SessionStart with source `compact` adds it to the resume note**, in the "Context was compacted" line, as "Before the compact the user asked: ...". It stays inside the 1,200-character note cap; it is one of the parts the cap cuts first.
3. **Nothing is saved without an active task** or without a readable transcript. Codex is unchanged (its PreCompact output is ignored). Any error saves nothing and the hook still exits 0.
4. **`note.carryAfterCompact`** (default `true`) turns it off.
5. **Not built:** a 15-minute expiry (the note is rebuilt from files at each SessionStart and the text is read only when the source is `compact`), a bullet cap and a check against the summary (the note cap and the "Summary kept N of M plan steps" line already cover them).

## Why

PreCompact already asks the summarizer to keep the latest request (ADR-0011) and the open work (P-25). That is a request, and a summary can drop them. After an auto-compact with no `wrap up`, they are the only record of what was in progress.

## Cost

A prompt's first 250 characters are written to a git-ignored local file until the next compact in that session overwrites it. They are redacted the same way as the PreCompact text.
