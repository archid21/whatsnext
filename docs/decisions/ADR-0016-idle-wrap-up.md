# ADR-0016: An opt-in idle timer submits `wrap up` before Claude Code's idle compact

- **Date:** 2026-11-07T07:52Z
- **Status:** accepted (user), 2026-11-07

Builds on ADR-0008 (`wrap up`) and ADR-0015. Claude Code only.

## Decision

1. **Setting `wrapup.autoIdle`, default `false`.** Off means nothing below runs.
2. **Timer: 45 minutes** after the last main-thread turn ends, kept by the hooks module (`hooks/register.tsx`, `$.clock.after`). Any submitted prompt stops it; the next turn end starts it again.
3. **It submits the exact prompt `wrap up` only when all of these hold:**
   - the setting is on;
   - the folder is a whatsnext project;
   - this session has no fresh wrap-up (ADR-0008: the note's sidecar matches and no turn came after it);
   - Claude Code's `idleCompaction` and `autoCompactEnabled` are not `false`;
   - the context is at or above `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS` (default 200000, never under 100000).
4. **Once per idle period.** After it submits, no timer starts until the person sends a prompt of their own (origin `composer` or `bridge`, or none). A notification or a scheduled run does not count.
5. **The check is split.** The module reads what only it can (context size, Claude Code's settings, the environment variable). `whatsnext hook idle-check` decides the whatsnext side and prints `{"fire": true|false}`. On `true` it writes the UTC time to the git-ignored `.whatsnext/sessions/<session>.idle.json`. Any error means no `wrap up`.
6. **Nothing here depends on rightsize.** Its keep-warm pings did not reset Claude Code's idle timer (14 pings, one every 4 minutes: the compact still came at 54:00).

## Why 45 minutes

Claude Code's idle compact (log line: "Compacted while idle, before the prompt cache expired"; the docs say "about an hour") came 54:00 after the last main-thread request in both tests, 2026-11-06 and 2026-11-07 UTC. 45 minutes leaves 9 minutes of margin, and fewer people who come back at minute 40 to 45 meet a surprise turn than with a 40-minute timer.

## Why it is opt-in

It starts a model turn nobody typed. That costs tokens: the wrap-up turn re-reads the context, and with a cold prompt cache the cost is the whole context at the uncached price. It also writes or replaces `docs/project/HANDOFF.md`. A person chooses that.

## Not known yet

Whether the wrap-up turn resets Claude Code's idle clock, so that the compact comes 54 minutes after the wrap-up and not after the original last request. The result of the harness run is in `docs/project/progress/P-40.md`.
