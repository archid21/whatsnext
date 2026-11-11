# ADR-0025: One command lets rightsize offer wrap up and start fresh

- **Date:** 2026-11-11T03:40Z
- **Status:** accepted (user), 2026-11-11; the band buttons and the desktop start_session path are superseded by [ADR-0026](ADR-0026-wrap-up-band-compact-or-paste.md)

Builds on ADR-0024 (start fresh after a wrap-up) and ADR-0009 (`compact-instructions`). P-69. rightsize's matching decision: its ADR 0050 (proposed).

## Decision

1. **New command:** `whatsnext fresh-instructions --session <id> --json`. It is read-only and prints everything a caller needs to wrap up and start fresh:
   - `project`, `session_found`, `handoff`, `handoff_exists`, `handoff_foreign`, `wrap_up_first`, `wrap_up_state`: the same values `compact-instructions --json` gives, from the same code.
   - `wrap_up_prompt`: `wrap up`.
   - `continue_prompt`: the new chat's first prompt, `Continue from the handoff note: read it first.`
   - `new_session_prompt`: the prompt that asks the agent to start a new session in the desktop app (ADR-0024 item 2).
   - `terminal_command`: `claude "Continue from the handoff note: read it first."`, for a new terminal window.
   - `clear_command`: `clear` (the command the caller runs before `continue_prompt`).
   Without `--json` it prints the three start-fresh texts as plain lines.
2. **The Python script is the one source of these texts.** `hooks/newchat.ts` keeps a copy for the band; a test fails when the two differ.
3. **How rightsize uses it** (rightsize decides when; whatsnext says how):
   - `project` false: rightsize offers only Compact now, as today.
   - `wrap_up_first` true: rightsize submits `wrap_up_prompt` as the person's prompt. When that turn ends with the note written, whatsnext's own band offers **New session** and **Clear and continue** (ADR-0024). rightsize shows nothing more.
   - `wrap_up_first` false (this session's note is fresh): no wrap-up turn runs, so whatsnext's band does not show. rightsize shows the two choices itself and runs them with the texts above: `new_session_prompt` (desktop) or `terminal_command` (terminal), or `clear_command` then `continue_prompt`.
   - Less room left than rightsize's `WRAP_HEADROOM` (40,000 tokens): no wrap-up turn; rightsize offers Compact now only, as today.
4. whatsnext writes no rightsize file and reads none.

## Why

rightsize's context warning offers only **Compact now**. A compacted chat keeps a summary of a long chat; a fresh chat seeded with the handoff starts small and is cheaper per turn. ADR-0024 made starting fresh one click after a wrap-up, but only when the person typed `wrap up`. rightsize knows when the context is large, so its warning is the right place to offer it. One command keeps rightsize from copying whatsnext's texts and rules.

## Trade-offs

- whatsnext's band reacts to any prompt that is exactly `wrap up`, so a prompt rightsize submits counts the same as a typed one. To check in a real session: that the engine's `prompt.submit` event fires for a prompt another plugin submitted.
- With a fresh note, two plugins hold the same two buttons' logic. The texts stay in one place (item 2); the button code is short.
- Codex has no band and no rightsize; the command works there but nothing calls it.
