# ADR-0001: whatsnext keeps a plan, a resume note and a handoff, and nothing else

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

## Decision

1. **What it is.** A plugin for Claude Code and Codex that keeps a shared plan, check-offs, per-task progress and a handoff note as plain files in the repository, so a new session or a second agent starts from where the last one stopped.
2. **What it is not.** It does not keep memory across projects, search past conversations, write decision records, manage ground rules, or run the work. Memory plugins, adr-kit, `CLAUDE.md` and `AGENTS.md` do those jobs. whatsnext reads nothing from them and needs none of them.
3. **Standalone.** It is the only plugin of its kind in this repository and owns the plugin name `whatsnext`. It needs no other plugin. It does more with rightsize (ADR-0010) and works without it.
4. **No model call of its own.**
5. **Standard library only, Python 3.9+.** No database, no background process, no network call.
6. **Files are the source of truth.** Markdown and JSON in the repository, readable and editable by hand (ADR-0002).
7. **Local first.** It never pushes and never creates a remote. Outside the repository it writes only under `~/.config/whatsnext/`.

## Not in this release

Cross-machine claims, a model-written turn summary, a search index, tracker adapters (GitHub, Beads, Jira), folders without git, harnesses other than Claude Code and Codex, a checklist pane. Each needs a new decision before it is built.

## Why

A market check on 2026-11-04 found memory, decision records and handoff notes each covered by established tools. What remains is the combination of a plan, a proven check-off and a resumable handoff, kept small and dependency-free. Keeping scope narrow keeps it cheap to maintain.

## Trade-offs

- Users who want memory or decision records install another tool.
- A narrow scope means a small audience; success is measured by use, not reach.
