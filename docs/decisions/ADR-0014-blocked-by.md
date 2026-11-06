# ADR-0014: A plan item may say which open items it waits for, and `plan next` skips it

- **Date:** 2026-11-06T22:12Z
- **Status:** proposed (agent), awaiting the user's decision

Amends ADR-0002, which lists `blocked by:` under "Not in this release".

## Decision

1. **One optional field.** A plan line may carry `· blocked by: P-3, P-5`, before or after `done means:`. Ids are plan item ids. A line without it is unchanged.
2. **`plan next` skips a blocked item** while any item it names is still open (unchecked). When nothing else is left it says so: "Nothing ready in Now or Next: P-1 waits for open items".
3. **`plan list --json` and `plan next --json`** carry `blocked_by` (the ids written) and `blocked_on` (those still open).
4. **`plan check` warns** on a `blocked by:` id that is not in the plan, and on an item blocked by itself.
5. **Nothing is enforced.** `plan start P-N` still starts a blocked item when the person or agent names it. The field only shapes what `plan next` recommends.

## Why

The agent asks "what's next?" and gets an item whose input does not exist yet. One field and one filter fix that without a scheduler.

## Trade-offs

- A cycle (P-1 waits for P-2, P-2 for P-1) leaves both out of `plan next`; the message names them. `plan check` catches only a direct self-block.
- A free-text id can be mistyped; `plan check` catches an id that is not in the plan.
