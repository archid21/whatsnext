# ADR-0009: A compact keeps what the handoff note says; closed-session compacting is not in the public release

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

Terms. **Open session**: a Claude Code session a live process holds. **Closed session**: one no live process holds. **Compact**: Claude Code's `/compact`, which replaces a long conversation with a summary.

## Decision

1. **Open session: whatsnext prints the text; the caller submits it.** `compact-instructions [--session <id>] [--json]` prints what to keep (the current task, decisions, open questions, file paths, next steps) and what to drop (tool output, dead ends), then adds the handoff note cut at 3,000 characters. whatsnext never submits a prompt into another process.
2. **One-line form.** `--json` returns `compact_line`, the finished `/compact <text>` built by code from the note: Goal 200, Next 300, Constraints 600, Decisions 400 and Blockers 300 characters, at most 1,800. Next and Constraints are never cut to make it fit. It is `null` when this session has no note.
3. **Wrap up first.** `wrap_up_first` is true when this session has no fresh note (missing, foreign or older than the last turn). The caller submits `wrap up`, waits for the turn to end (`wrap_up_state` is then `written`), and asks again, because the text includes the note.
4. **A foreign note is never carried** (ADR-0008).
5. **Closed sessions are not in the public release.** Compacting a closed session with Haiku (`compact --session`), the queue of ended sessions, the compact log and the `compact.closed.*` settings stay on the `closed-compact-eval` branch. That branch collects the data below. Nothing in the public release compacts without the person.
6. **When to build it.** The closed-session worker is built only when measured data shows it pays: the value rule is p × (the cold cost avoided) ≥ 2 × (the compact cost), where p is the measured return rate per size bucket. Until 30 sessions are measured, p = 0.06, and at that rate no size qualifies. When built, the worker runs from the SessionStart sweep, not from SessionEnd (that hook times out at 5 seconds and a process it starts may die with it), and it is opt-in.

## Why

Code that builds the compact text from a fixed structure means the summary keeps what the person wrote down, not what a model guessed. Spending money on closed sessions waits for evidence that sessions come back.

## Trade-offs

- A person who wants closed-session compacts now runs the branch or does it by hand.
- The data comes from the owner's own sessions, which may not match other people's.
