# ADR-0018: SessionStart removes the state files of sessions idle for 14 days

- **Date:** 2026-11-09T06:53Z
- **Status:** accepted (user), 2026-11-09

Builds on ADR-0005 (per-session state in `.whatsnext/sessions/`) and ADR-0008 (handoff sidecars).

## Decision

1. **When:** at every SessionStart in a whatsnext project, before the resume note is built. A failed prune never stops the note.
2. **What goes:** the per-session files the hooks write, `<id>.json`, `<id>.handoff.json`, `<id>.compact.json`, `<id>.idle.json`, `<id>.resume.json`, `<id>.wrapup.json`, `<id>.summary.json`, `<id>.summary.md` and `<id>.summary.md.bak`, for a session none of whose files has changed in 14 days (`SESSION_KEEP_DAYS`).
3. **What stays:** the starting session's files; any session with one file newer than 14 days (all its files stay); `health-*.json` (`doctor`'s evidence); `capture.unreadable.json`; every other name; links, which are never followed or removed. Nothing is pruned when the folder or `.whatsnext` is a link.
4. **Committed history is not touched:** progress files, journals and the handoff archive (which keeps its own last 10, ADR-0008).

## Why

The folder only grows: 101 files in this repository after 5 days. It is git-ignored, so the cost is disk and clutter, not commits. A session's files are read only while that session runs or soon after a compact; 14 days leaves room for a session resumed after a long break.

## Why SessionStart

It runs in every agent (Claude Code and Codex), once per session, and already reads the project. `wrap up` and `doctor` run too rarely to keep the folder small.
