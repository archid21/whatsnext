# ADR-0028: a drift note when work moves off the claimed item

- **Date:** 2026-11-16T22:35Z
- **Status:** accepted (user), 2026-11-16

Extends ADR-0005 (hooks and the journal) and ADR-0027 (any agent). For P-73.

## Context

A session claims one item with `plan start`. Over a long session the work can move to something else, such as a refactor, a second bug or a different feature. The journal, the verify run, the handoff and the PR body then credit the claimed item with that work. Two sessions in one folder are told to stay on their own items, and drift is how they start to collide.

The Stop hook already lists the files each turn changed, so the facts exist without a model call. Each progress file has a `Files:` line meant for the paths the item touches. In practice it is usually `none`: an empty list cannot tell drift from normal work.

## Decision

1. **Learned file list.** While an item's `Files:` line is `none`, whatsnext records the folders the item's work touches during its first 3 turns that change files (the item's *scope*), in the session state under `.whatsnext/sessions/`. A `Files:` line set by `progress stamp --files` replaces the learned scope. Matching is by folder: a file is in scope when it is in a listed file's folder or under a listed folder.
2. **The check.** At turn end (Stop, or the agent's mapped turn-end event), whatsnext compares the turn's changed files with the scope of the item this session claimed. Files in `docs/project/` (plan, progress, handoffs, journal) never count. Without a claimed item there is no check.
3. **One note, never a block.** When files outside the scope changed, whatsnext gives one note: "N files changed outside P-12 (a, b, …). Add them to P-12 (`progress stamp P-12 --files …`), or plan them as new work?" The same set of out-of-scope files gives the note once; a new file outside the scope gives it again. The turn always ends normally and nothing is written to PLAN.md.
4. **Where the note shows.** Claude Code: the band above the prompt. Other agents: the turn-end hook output where the agent shows it, and a line in `status` warnings while it is not answered. Hook-free agents see it only in `status`.
5. **Answers.** Add the files to the item (`progress stamp --files`), plan the work as new items (plan from a goal), or ignore it. Ignoring the note is fine; it is not shown again for the same files.
6. **Setting.** `plan.driftNote` is `on` (default) or `off`, set with `config set --user plan.driftNote off`.

## Consequences

- The journal, verify, handoff and PR body stay about the claimed item, or the user knows when they are not.
- The first turns of an item are trusted to be on scope. Drift in those turns is not caught.
- Folder matching misses drift inside one folder and can flag a related file in a new folder. Setting `Files:` by hand fixes both.
- One more band message competes with the wrap-up band and the tips; it is shown at most once per new file set.

## Alternatives

- **No note until `Files:` is set by hand:** no false alarms, but almost no item has the line, so it would almost never run.
- **Every file outside an empty list:** every change is drift, so the note is noise.
- **Block the turn, or ask before continuing:** stops real work for a guess; whatsnext never blocks on a heuristic.
- **Ask a model whether the work fits the item:** a model call at every turn end, slow and not repeatable.
