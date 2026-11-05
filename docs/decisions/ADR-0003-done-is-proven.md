# ADR-0003: Done means a command passed, or the person said so

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. `plan done <id> --verify "<cmd>"` runs the command from the project root. Exit 0 ticks the item and records `verified: <cmd> passed in <n> s (<UTC>)` as evidence. Any other result leaves the item open and journals the last 20 lines of output.
2. A command that runs longer than `plan.verifyTimeout` (30 minutes) is stopped and counts as a failure.
3. `plan done <id> --evidence "<text>"` ticks an item that no command can check. It shows as `done*` (checked by a person, not verified), and `plan list` explains the mark once.
4. `--verify` and `--evidence` are not combined. `--unverified` ticks with no evidence, and only when the person asks.

## Why

An agent saying "tests pass" is a claim. A recorded command and its result is evidence, and the two kinds are visibly different.

## Trade-offs

- The command runs on the person's machine with their permissions; a verify command comes from the plan or the person, never from repository text the agent has not been told to trust.
- A passing command proves only what the command tests.
