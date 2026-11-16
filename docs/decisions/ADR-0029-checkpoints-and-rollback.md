# ADR-0029: a git checkpoint at each item start, and a rollback that never loses work

- **Date:** 2026-11-16T23:03Z
- **Status:** accepted (user), 2026-11-16

Extends ADR-0005 (hooks and the journal) and the Start flow. For P-71.

## Context

When an item goes wrong, the user wants it undone. Any agent can do this with git today, but it has to guess where the item started (branch base, journal, log), and a guess on a shared or merged branch is easy to get wrong. Agents can also run `git reset --hard` or `git checkout .` and lose uncommitted work. Nothing in whatsnext records the start point or guards the undo.

## Decision

1. **Checkpoint at start.** `plan start <id>` records the commit it started from as the local ref `refs/whatsnext/checkpoints/<id>`, plus the branch name and time in the item's progress file (`Checkpoint: <short sha> on <branch>, <UTC>`). A restart of the same item keeps the first checkpoint. Refs are local: whatsnext never pushes them.
2. **`plan rollback <id>`.** It shows what it would undo (the commits since the checkpoint on the item's branch, and the files they change) and asks before it changes anything (exit 4, answer `--yes`). It picks the method:
   - **Reset** (the item has its own branch, and the branch is not merged): move the branch back to the checkpoint.
   - **Revert** (the item shares a branch, other commits are mixed in, or the branch is merged into `main`): add new commits that undo only the item's commits. History is never rewritten on a shared or merged branch.
   The question names the method and why; `--method reset|revert` overrides it only where reset is safe.
3. **Uncommitted work is never dropped.** If the working tree has changes, rollback asks first: **stash them (recommended)**, commit them, or cancel. A stash is labeled `whatsnext rollback <id> <UTC>` and includes untracked files; the answer says how to bring it back (`git stash pop`). With no answer, nothing happens.
4. **After a rollback.** The item stays in the plan and is open again (a done item is reopened with the reason "rolled back", as `plan reopen` does). Its claim is released. The journal gets a `rollback` line with the method and the commits undone. The checkpoint ref stays, so a second rollback works.
5. **Limits.** Rollback refuses when the checkpoint commit is gone, when a merge or rebase is in progress, or when the item has no checkpoint (items started before this release): it then prints the git commands to do it by hand. It never pushes, never deletes a branch, and never runs `git clean`.

## Consequences

- "Roll back P-12" is exact and the same in every agent.
- One more local ref per started item. They are tiny; `git for-each-ref refs/whatsnext/checkpoints` lists them.
- Revert on a shared branch can conflict; rollback then stops, leaves git in the revert state, and says how to finish or abort (`git revert --abort`).
- Work outside git (databases, deployed services) is not rolled back; the answer says so.

## Alternatives

- **Let the agent use git by hand:** works, but the start point is a guess and nothing guards uncommitted work.
- **Always reset:** simplest, but rewrites shared or merged history.
- **A tag instead of a ref under `refs/whatsnext/`:** tags show up in `git tag` and are pushed by `--tags`.
- **Stash without asking:** safe, but surprising; the user should know where the work went.
