# ADR-0007: `init` is additive and reversible

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **Git repositories only.** `whatsnext init` creates what is missing and never overwrites a file.
2. **It owns five things:** the plan file, `.whatsnext/config.json`, the progress folder with its journal folder, the `.whatsnext/sessions/` line in `.gitignore`, and one block in `AGENTS.md` between `<!-- whatsnext:start -->` and `<!-- whatsnext:end -->`, appended and never replacing text.
3. **It prints where the plugin's hooks are** instead of installing them.
4. **Preview and undo.** `--dry-run` prints the plan and writes nothing. `--undo` removes only the `AGENTS.md` block (and the file itself when nothing else is left in it) and leaves the person's other files.
5. **A whatsnext project** is a folder where the progress module is on and `.whatsnext/` or the entry file exists. Hooks and `wrap up` act only there.

## Not in this release

Importing an existing plan, capturing a first progress file from git history, `CLAUDE.md` and `.gitattributes` edits, folders without git.

## Why

A tool that edits a repository must show what it will change first and be able to take it back.

## Trade-offs

- A repository with an existing plan starts with an empty `PLAN.md`; the person moves items over by hand.
