# ADR-0002: The plan and progress files, with trust marks and soft claims

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **The plan** is `docs/project/PLAN.md` (`paths.plan`): one line per item, `- [ ] P-N Title · done means: <how we know>`, under `## Now`, `## Next` and `## Later`. `plan check` reports items with no done means and duplicate ids.
2. **One progress file per task**, `docs/project/progress/<id>.md` (`paths.progress`). It holds the state, the branch, `## Done`, `## Next action`, the plan steps and `## Since wrap-up`. Every file starts with `format: 2`; a file with a higher format is refused.
3. **Trust marks.** The header's `Note:` is `confirmed` (the person said it, or a command passed), `auto` (a model guessed it) or `facts` (the hooks wrote it from git). `progress next <id> "<text>"` sets a confirmed Next action. A guess (`--auto`) never replaces a confirmed one; it goes under `## Since wrap-up`.
4. **Soft claims.** `plan start` records a claim in `<git common dir>/whatsnext/claims/<ID>.json`, so every worktree of one clone sees it. Claims are never committed. When the git folder cannot be written (Codex's sandbox protects `.git`), the claim goes to `.whatsnext/claims/` instead, which holds its own `.gitignore`; reads check both folders, and a claim in the fallback folder is not visible from another worktree. A claim is a note, not a lock: it goes stale after `plan.staleAfter` (4 hours) and the holder is asked to keep, put back or finish it.
5. **Start asks only what it must.** Questions come in this order: takeover (another agent holds the item), done means (missing), uncommitted changes, the item already in progress, the branch. A command that needs an answer prints the question and exits 4; the agent asks once and runs the command again with the answer flag. Nothing is marked in progress until the checks pass.
6. **Private text stays out.** Text in `<private>` tags is removed before any write of user text, and secret-looking text gives a warning.

## Not in this release

Claims committed to the repository, a merge driver, a ready queue with `blocked by:`, one rolling item for handoff-only use.

## Why

Plain files survive without the tool and work for any agent that can read a file. Trust marks make a wrong note visible instead of trusted. Claims kept out of the repository avoid merge conflicts, at the cost of not crossing machines.

## Trade-offs

- Two clones, or two machines, do not see each other's claims.
- Five possible questions at Start is more than a silent default would ask; each guards a real conflict.
