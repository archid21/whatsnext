# ADR-0012: A plan item may carry a `suggest:` hint that whatsnext stores and never uses

- **Date:** 2026-11-06T19:04Z
- **Status:** accepted (user), 2026-11-06

Amends ADR-0010 item 3 (the JSON contract) with one field.

## Decision

1. **One optional field.** A plan line may end with `· suggest: <model>/<effort>`, for example `· suggest: sonnet/high`. The field may sit before or after `done means:`. A line without it is unchanged.
2. **whatsnext stores it as written.** It does not check the value against a list of models, and it never picks, changes or enforces a model or effort.
3. **It is shown, not used.** `plan next --json`, `plan list --json` and the `plan start` output carry a `suggest` string (empty when none). rightsize reads it there, not from PLAN.md (ADR-0010 item 1). rightsize decides whether to use it, and its own choice wins.
4. **It is a hint from planning time.** The agent that writes the plan fills it. It can be out of date after the item changes.

## Why

A planning session can rate each item once, and each later session then starts from the item with that rating. Storing one string costs almost nothing. Choosing models stays in rightsize.

## Trade-offs

- The contract grows by one field; a change must be announced to rightsize (ADR-0010).
- The plan and rightsize can disagree. This ADR says rightsize wins.
- A free-text value can be misspelled. whatsnext does not catch that.
