# ADR-0023: Mark done can reuse a recent passing run of the same check

- **Date:** 2026-11-10T20:46Z
- **Status:** accepted (user), 2026-11-10

Amends ADR-0003 (done means a command passed, or the person said so). P-66.

## Decision

1. `plan test <id> [CMD]` runs the item's saved check, chosen by the same rules as `plan done --verify` (ADR-0017), and prints the last 20 output lines. It never ticks the item.
2. Every run of `plan test` and `plan done --verify` is saved in `<git dir>/whatsnext/runs/`: the command, pass or fail, seconds, time (UTC) and the code fingerprint (the `code_state` hash `plan done --verify` already records, P-8). The newest 20 runs are kept.
3. `plan done <id> --verify` reuses a saved pass instead of running the command when all of these hold: the command is the same exact text, the code fingerprint is the same now, and the run is newer than `plan.reuseRunMax` (default `60m`). The evidence then reads `verified: <cmd> passed in <n> s (reused run of <UTC>)`, followed by the time and code state as before.
4. The fingerprint covers file content, not the commit: "run the tests, commit, mark done" reuses the run. Any changed, new or deleted file, other than whatsnext's own files (the plan, progress files, `.whatsnext/`), means a fresh run.
5. `plan done <id> --verify --fresh` always runs the command.

## Why

The full suite takes 6 to 8 minutes. The usual flow runs it once to check the work and again at mark done, on the same code. The second run proves nothing new.

## Trade-offs

- A reused pass is only as good as the fingerprint. Something outside the files (an installed package, the clock, the network) can change between the two moments. `--fresh` is there for checks that depend on such things.
- The run store is in the git folder, like claims: never committed, never shared, and writable by anyone who can write the repository. That is the same trust as running the command itself.
- An older run than `plan.reuseRunMax` is never reused, even with the same fingerprint.
