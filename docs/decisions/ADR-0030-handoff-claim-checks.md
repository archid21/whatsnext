# ADR-0030: re-check the handoff's claims at resume

- **Date:** 2026-11-18T21:50Z
- **Status:** accepted (user), 2026-11-18

Extends ADR-0008 (the handoff note) and P-23 (`handoff verify`). For P-87. Idea from warrant.

## Context

A handoff says things like "HEAD is d762f03" and "the tests pass". The next session trusts them. When the code moved since, the note is wrong and nothing says so.

## Decision

1. **`Check:` lines.** Wrap-up asks for `Check:` lines at the end of `## State`, one fact each, in a fixed form:
   - `Check: HEAD == <short sha>`
   - `Check: branch == <name>`
   - `Check: clean` (no uncommitted changes)
   - ``Check: run `<command>` `` (exit 0 means the claim holds)
2. **Three verdicts.** VERIFIED (the check ran and agrees), STALE (the check ran and disagrees), BROKEN (the check could not tell: exit 126 or 127, a timeout, git missing, or a line in no known form).
3. **What runs where.** `status` checks only the git facts (HEAD, branch, clean): they run no project command. A `run` check runs only in `handoff verify --run-checks`, which the person starts. Each command is printed before it runs. For a git-tracked note, the refusal lists every `run` command with the `Verify:` command, and both flags are needed (`--allow-tracked --run-checks`). Text from the note is cleaned of control characters before it is shown, and the `Agent:` header is shown only when it is a plain name. `status` lists a `run` check as "not run".
4. **plan done --verify.** Exit 126 or 127 (command not runnable or not found) or a timeout is recorded as `verify broken`, apart from `verify failed`, in the journal and the message. The item stays open in both cases. The plan report counts broken runs apart.
5. **No model call.** Checks are parsed and run by code only. Python 3.9, standard library.

## Consequences

- A resume shows at once when the note's facts are out of date.
- A note from someone else's commit cannot make `status` run a command.
- Notes without `Check:` lines work as before.
