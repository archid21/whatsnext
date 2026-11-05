# ADR-0006: A plan-mode plan is stored word for word and attached to its task

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **Command.** `progress capture [<task-id>] --agent <name> --status shown|approved|unapproved [--file <path>]`. The text comes from `--file` or stdin; the task is the active one unless named. A failed capture never blocks the agent.
2. **Statuses.** `shown` stores the plan and writes its steps. `approved` and `unapproved` only change the status of a plan that is still `shown`; on any other plan the command prints "already <status>; unchanged" and exits 0, so a hook can send `unapproved` on every prompt after plan mode ends.
3. **Store.** `docs/project/plans/<task-id>-<YYYY-MM-DD>.md` (`paths.plans`), starting with `Agent`, `Time` (UTC) and `Status` lines, then the plan word for word. A new `shown` plan replaces a `shown` file of the same name; an approved or unapproved plan is never overwritten (the next file ends `-2`, `-3`).
4. **Steps.** Plain code splits the plan by `##` headings, then by numbered items, then by `- ` items, else one step. At most 20 steps go under `## Plan steps` in the progress file; more are noted as "… N more in the plan file". A new capture replaces the section.
5. **The note says so.** The progress file's `Plan:` field holds the path and status. The resume note adds the plan's step and, when the plan is not approved, "used without approval" (ADR-0004).
6. **The roadmap is untouched.** Capture never edits `PLAN.md`. The agent asks the person one question before adding an item from a stored plan.
7. **No model call.** The text is redacted like any write (ADR-0002).

## Why

An approved plan is the record of what the person agreed to. Storing it unchanged, and keeping it separate from the roadmap, keeps one source of truth for each.

## Trade-offs

- A plan written as prose splits into poor steps.
- Stored plans are copied as written; the person should read them before a push.
