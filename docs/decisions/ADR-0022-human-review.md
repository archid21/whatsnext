# ADR-0022: An item can need a person's review after its check passes

- **Date:** 2026-11-10T18:26Z
- **Status:** accepted (user), 2026-11-10

Amends ADR-0003 (done means a command passed, or the person said so). P-58.

## Decision

1. An item opts in with a `review: required` field in PLAN.md, written like `blocked by:` and `suggest:`. Items without the field work as before.
2. `plan done <id> --verify` on such an item runs the check as ADR-0003 and ADR-0017 say. A pass records the run as evidence but leaves the box unchecked. The claim is released, the progress file State is `review`, and `plan list` shows `awaiting review`. `plan next` and `status --json` `ready` skip the item. A failed run changes nothing, as before.
3. `plan review <id>` ticks the item and adds `reviewed: <UTC>` after the recorded run. `plan review <id> --reject "<reason>"` sends the item back to open: the old run stays in the evidence as `rejected: <reason> (<UTC>)`, and only a fresh `--verify` can make it await review again.
4. An agent runs `plan review` only after the person approves (or rejects) in chat, as with `--unverified` today. `--evidence` and `--unverified` on an item that needs review are refused: a person's word is the review, so they use `plan review`.

## Why

A passing command proves what the command tests. Some items also need a person to look (a UI, copy, a design). Without a separate state, an agent ticks the item when tests pass and the person's check is lost.

## Trade-offs

- One more status to read in `plan list`. Only items that opt in can reach it.
- `plan review` is a person's word, recorded by an agent. The rule in point 4 is a convention the agent follows, not something the script can prove.
- The check can go stale while the item waits. `plan check` warns about drift for checked items as before; it does not yet warn for items awaiting review.
