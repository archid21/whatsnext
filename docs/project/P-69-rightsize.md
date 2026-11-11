# P-69: the rightsize side

What to change in rightsize so its context warning offers **Wrap up and start fresh** next to **Compact now**. whatsnext's side is [ADR-0025](../decisions/ADR-0025-start-fresh-from-rightsize.md) and the command `fresh-instructions --session <id> --json`. Written 2026-11-11T03:55Z, against rightsize branch `p-10-output-advice-suggest-the-concise-output`.

## 1. Draft ADR for rightsize: `docs/decisions/0050-start-fresh-from-the-context-warning.md`

```markdown
# 50. The context warning offers wrap up and start fresh

Date: 2026-11-10 (Pacific). Status: proposed.

Amends 0013 decision 1 (the context-size warning). Matches whatsnext ADR-0025.

## Decision

1. When whatsnext is installed and `project` is true, the context-size warning has a second button, **Start fresh**, next to **Compact now**. The usage-limit advice keeps **Compact now** only: before a reset a compact is the cheaper move.
2. **Start fresh** runs `whatsnext fresh-instructions --session <id> --json` (through `whatsnextRun`) and follows it:
   - `wrap_up_first` true and more than `WRAP_HEADROOM` (40,000) tokens left: submit `wrap_up_prompt` as the person's prompt. whatsnext's band then offers New session and Clear and continue. rightsize clears its row and shows nothing more.
   - `wrap_up_first` true and less room than that: no wrap-up turn; the button says the handoff could not be written and offers Compact now.
   - `wrap_up_first` false: the row shows **New session** and **Clear and continue**. New session submits `new_session_prompt` as the person (desktop app) or shows `terminal_command` (terminal). Clear and continue runs `clear_command`, then submits `continue_prompt` as the person.
   - Any error, or `project` false: only Compact now, as today.
3. rightsize copies none of whatsnext's texts; they come from the command each time.

## Why

A compacted chat still carries a summary of a long one. A fresh chat seeded with the handoff starts small, so each later turn costs less. The warning already fires when the context is large, which is when this choice matters.

## Trade-offs

- One more button on the row. "Why?" explains both.
- In the terminal, New session can only show a command to copy.
```

## 2. Code points (rightsize `plugins/rightsize/hooks/`)

1. `size.ts`: add `SIZE_FRESH = 'size-fresh'` and `SIZE_FRESH_BUTTON = { id: SIZE_FRESH, label: 'Start fresh' }`; add it to `isSizeId`. Update `SIZE_WHY` to say what Start fresh does.
2. `register.tsx`, `sizeCheck` (about line 2840): pass the second button to `showAdvice` only when `whatsnextInstalled($)` and `whatsnextInitialized($)` are true. `showAdvice` takes one `button` today, so it needs a `buttons` list (or a second field).
3. `register.tsx`, `pressSize` (about line 2875): handle `SIZE_FRESH` the way `SIZE_COMPACT` is handled (refuse while `mainBusy`), then call a new `freshForSize($)`.
4. `freshForSize($)`: run `whatsnextRun($, ['fresh-instructions', '--session', sessionId, '--json'])`, parse it the way `whatsnextSteps` parses `compact-instructions` (line 2666), then follow decision 2 above. Submit prompts with `$.prompt.submit({ text, asUser: true })`; run `clear` with `$.command.run({ command: 'clear', args: '' })` (a prompt that begins with `/` is refused).
5. `whatsnext.ts`: no new copy of whatsnext's text. A constant for the button label only.

## 3. Tests to add in rightsize

- `size.test.ts`: `isSizeId('size-fresh')` is true.
- `register.size.test.ts`: the warning shows Start fresh only when whatsnext is installed and `project` is true; `wrap_up_first` true submits `wrap up`; false shows New session and Clear and continue; Clear and continue runs `clear` and then the continue prompt; a whatsnext error leaves only Compact now.

## 4. To check in a real session

- whatsnext's band appears after a `wrap up` that rightsize submitted (ADR-0025 trade-off: `prompt.submit` must fire for a prompt another plugin sent).
- New session in the desktop app starts the session; Clear and continue keeps the old chat in `/resume`.

## 5. Closing P-69 (in whatsnext)

P-69 is done when: ADR-0025 (whatsnext) and 0050 (rightsize) are accepted, the rightsize change is in, and `python3 -m unittest discover -s tests` passes in whatsnext. Then run `plan done P-69 --verify` from the whatsnext root.
