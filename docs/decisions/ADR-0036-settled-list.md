# ADR-0036: A settled list: choices already made, copied from the handoff by code, so later sessions do not reopen them

- **Date:** 2026-11-21
- **Status:** proposed

Builds on ADR-0008 (the handoff note), ADR-0013 (Dead ends) and ADR-0035 (handoff from a transcript). For P-93. An agent's suggestion: it stays `proposed` until the user accepts it.

## Context

A new session reads the handoff note and then often tries again what an earlier session already dropped, asks again about a tool the user already chose, or reports as a fault something that is normal. The note's Dead ends section holds only the last session's dropped approaches; the next wrap-up overwrites it. Nothing keeps these choices after two or three sessions.

## Decision

1. **A tracked file, `docs/project/SETTLED.md`,** holds choices already made. One line each: `- <kind>: <text> (<source>)`.
   - `dropped`: an approach tried and rejected ("chose B over A, don't revisit A").
   - `use`: a tool or approach that must be used.
   - `expected`: recurring behavior that looks like a problem and is not (for example: the security plugin's `UserPromptSubmit` hook runs first, so a notice that another plugin's hook was skipped is expected).

   `<source>` is an ADR path or a handoff note path. The file is plain Markdown, in git, editable by hand.
2. **The handoff note gets a ninth section, `## Settled`,** after `## Dead ends`, in the same line format. `none` when nothing is new. At most 400 characters. The wrap-up instructions (`wrapup.instructions`) and the transcript helper prompt (`transcript.prompt`) ask for it. It is not in the `/compact` line. A note without the section is still valid (read as `none`); `handoff from-transcript --write` accepts an answer with or without it.
3. **Code copies the lines.** At the end of a wrap-up (`wrapup.settle`, the existing Stop-hook step that copies the Next action) and after `handoff from-transcript --write`, whatsnext parses the `## Settled` section and appends each valid new line to `docs/project/SETTLED.md`:
   - A valid line has kind `dropped`, `use` or `expected` and some text. `none` and malformed lines are skipped.
   - A line with no source (a path in the final parentheses) gets the handoff note's repository-relative path as its source.
   - A line is new when its kind and text, lower-cased with white space collapsed, are not already in the file. Re-running a wrap-up with the same lines adds nothing.
   - Each line goes through `redact.mask_secrets` (with emails) and is cut at 300 characters.
   - The file is created with a short header when missing. It is never rewritten when nothing is new, and a linked file is not written.
4. **The resume note shows it.** A `Settled:` part lists the newest lines (the end of the file), at most 5, each cut at 110 characters, then `(N more in docs/project/SETTLED.md)` when more exist. It shrinks before the Next action, Handoff and Run lines, and is the first optional part dropped after Done. Nothing is shown when the file is missing or has no valid line.
5. **No new hook entry** in `hooks/hooks.json` and **no model call.** The only model-written text is the `## Settled` section, which the agent writes as part of the note it already writes.

## ADR-0001 scope check

ADR-0001 item 2 says whatsnext does not "write decision records, manage ground rules". The settled list stays in scope for these reasons:

- **Copied, not authored.** Code copies lines from the handoff note the agent already wrote (ADR-0008). whatsnext does not decide what is settled and does not compose lines.
- **Each line points to its source.** The ADR or handoff note named in the line is the record. SETTLED.md is an index into records that adr-kit, the user or the handoff already hold; it is not a second record.
- **It stores no new rules.** It does not hold ground rules, preferences or instructions for the agent. `CLAUDE.md` and `AGENTS.md` keep doing that. A line says a choice was made, and where.
- **No model call (ADR-0001 item 4)** and **no new hook.** The copy runs in the Stop step that already exists; the transcript path runs inside a command the caller already calls.
- Standard library only, local files only (ADR-0001 items 5 to 7).

The line is close: a `use` line can read like a rule. The limit is that every line has a source and the file never holds a line the handoff did not carry. If the user reads item 2 more strictly, drop decision 4 and keep the file hand-edited, or drop the whole decision.

## Why

- A dropped approach and its reason are the costliest thing to rediscover (ADR-0013). That cost grows across sessions, and Dead ends covers one.
- Copying by code makes the list cheap to keep: the agent writes one more section, and nothing else changes.
- Dedupe by text means a repeated wrap-up does not grow the file.

## Trade-offs and risks

- **The list can go stale.** A choice may be reversed in a later ADR; the old line stays until someone edits the file. The source shows the date.
- **Model-written lines.** A wrong or invented line gets into a tracked file. The source column and git history make it reviewable; the resume note labels the lines as repository data, not instructions.
- **Hookless agents.** An agent with no Stop hook (ADR-0027, instructions tier) has no step that runs the copy after its wrap-up. Its `## Settled` section stays in the note until a Stop-hook agent, or `handoff from-transcript --write`, runs the copy. A command for this is not built here.
- **Resume note room.** The note's cap is 1,200 characters. The Settled part uses up to about 600 when full, so it shrinks first.
- **Growth.** The file only grows. Hand pruning is the fix; no limit is set here.
