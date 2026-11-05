# ADR-0008: `wrap up` writes a structured handoff note that belongs to the session that wrote it

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

Terms. **Handoff note**: one file that tells the next session where the work stands. **Foreign note**: a handoff note this session did not write.

## Decision

1. **A prompt the hook recognizes.** The `prompt-submit` hook matches the exact prompt `wrap up` (white space ignored, case kept) and prints instructions that tell the agent to write the note. A sentence that merely contains the words does nothing. In a folder that is not a whatsnext project it is a plain prompt.
2. **Path.** The `paths.handoff` setting, else a `Handoff: <path>` line in `AGENTS.md`, else `docs/project/HANDOFF.md`. An absolute path or one containing `..` is ignored.
3. **Structure.** Under `# Handoff`: `Session: <id>`, `Task: <id or none>`, `Written: <UTC>`. Then `## Goal`, `## Next action` (ending with a `Verify:` line), `## State`, `## What changed`, `## Decisions`, `## Constraints` and `## Open questions and blockers`. The hook supplies the times, so the model does not guess them.
4. **The agent ends its reply with** `Handoff written: <path>`, one line `/compact <text>` and "or `/clear` for a fresh start" (ADR-0009).
5. **Recorded at Stop.** If the note was written since the request, whatsnext records `session.wrapup`, adds a `wrap-up` journal line, writes `.whatsnext/sessions/<session>.handoff.json` (`sha256`, `path`, `written_epoch`), and copies the note's Next action into the active progress file as `auto`. It never replaces a confirmed Next action; the copy goes under `## Since wrap-up`. The agent runs no command, so no permission prompt can stop the wrap-up.
6. **Freshness belongs to the writer.** A note is fresh for a session only when that session's sidecar exists, its SHA-256 is the file's now, and no turn came after the file was written. Any other note, including one written before the sidecar existed or edited by hand, is foreign. A foreign note is never carried into a compact; the text says another session wrote it and gives its path.
7. **The resume note** adds `Handoff: <path> (read it first)` when the note's `Session:` is this session or its `Task:` is the active task, else `Handoff: <path> (another session's note)` (ADR-0004).

## Why

Two sessions in one project must not make each other's note look fresh. A fixed structure lets code, not the model, build what a compact keeps.

## Trade-offs

- A note costs one agent turn to write.
- Old or hand-edited notes count as foreign until the next `wrap up`.
