# Decisions index

Dates are UTC. This list is the current set of decisions for whatsnext. Earlier drafts, including the Groundwork-era ones, are in git history; an ADR number cited in a commit before 2026-11-05 means the earlier list.

| # | Date | Title | Status | File |
|---|---|---|---|---|
| 0001 | 2026-11-05T18:40Z | whatsnext keeps a plan, a resume note and a handoff, and nothing else | accepted (user) | [ADR-0001](ADR-0001-scope.md) |
| 0002 | 2026-11-05T18:40Z | The plan and progress files, with trust marks and soft claims | accepted (user) | [ADR-0002](ADR-0002-plan-and-progress-files.md) |
| 0003 | 2026-11-05T18:40Z | Done means a command passed, or the person said so | accepted (user) | [ADR-0003](ADR-0003-done-is-proven.md) |
| 0004 | 2026-11-05T18:40Z | The resume note is one short block the agent can continue from | accepted (user) | [ADR-0004](ADR-0004-resume-note.md) |
| 0005 | 2026-11-05T18:40Z | Hooks do the bookkeeping, record facts only, and never break a session | accepted (user) | [ADR-0005](ADR-0005-hooks-and-journal.md) |
| 0006 | 2026-11-05T18:40Z | A plan-mode plan is stored word for word and attached to its task | accepted (user) | [ADR-0006](ADR-0006-plan-capture.md) |
| 0007 | 2026-11-05T18:40Z | `init` is additive and reversible | accepted (user) | [ADR-0007](ADR-0007-init.md) |
| 0008 | 2026-11-05T18:40Z | `wrap up` writes a structured handoff note that belongs to the session that wrote it | accepted (user) | [ADR-0008](ADR-0008-wrap-up-and-handoff.md) |
| 0009 | 2026-11-05T18:40Z | A compact keeps what the handoff note says; closed-session compacting is not in the public release | accepted (user) | [ADR-0009](ADR-0009-compact.md) |
| 0010 | 2026-11-05T18:40Z | With rightsize, rightsize decides when and whatsnext decides what | accepted (user) | [ADR-0010](ADR-0010-working-with-rightsize.md) |
| 0011 | 2026-11-06T18:41Z | PreCompact reads the end of the transcript to keep the user's latest request | accepted (user) | [ADR-0011](ADR-0011-precompact-reads-the-last-request.md) |
| 0012 | 2026-11-06T19:04Z | A plan item may carry a `suggest:` hint that whatsnext stores and never uses | accepted (user) | [ADR-0012](ADR-0012-suggest-field.md) |
| 0013 | 2026-11-06T20:02Z | The handoff note has a Dead ends section, and the compact text keeps it | accepted (user) | [ADR-0013](ADR-0013-dead-ends-in-the-handoff.md) |
| 0014 | 2026-11-06T22:12Z | A plan item may say which open items it waits for, and `plan next` skips it | accepted (user) | [ADR-0014](ADR-0014-blocked-by.md) |
| 0015 | 2026-11-07T06:20Z | The resume note after a compact repeats the user's latest request and the open work | accepted (user) | [ADR-0015](ADR-0015-carry-after-compact.md) |
