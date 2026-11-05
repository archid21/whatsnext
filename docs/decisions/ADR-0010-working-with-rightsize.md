# ADR-0010: With rightsize, rightsize decides when and whatsnext decides what

- **Date:** 2026-11-05T18:40Z
- **Status:** accepted (user), 2026-11-05

Terms. **rightsize**: a separate Claude Code plugin that routes models, watches the prompt cache and usage windows, and shows a band with buttons.

## Decision

1. **The boundary.** rightsize decides when to wrap up or compact (cost, cache, context size) and shows the band and buttons. whatsnext decides what a compact keeps and writes every project file. rightsize writes nothing in the project and opens none of whatsnext's files.
2. **Each works alone.** whatsnext needs nothing from rightsize. rightsize falls back to its own fixed compact text when whatsnext is missing or the folder is not a whatsnext project.
3. **One JSON contract.** rightsize runs `compact-instructions --session <id> --json` and reads: `project` (true when whatsnext acts in the folder; it replaces any file check on rightsize's side), `wrap_up_first`, `wrap_up_state` (`requested`, `written` or `none`), `handoff`, `handoff_exists`, `handoff_foreign`, `wrap_up_prompt`, `compact_prompt`, `instructions`, `compact_line` and `session_found` (ADR-0009).
4. **rightsize submits one fixed text, `wrap up`,** only when whatsnext says a wrap-up is missing, waits for the turn to end, and asks again. It compacts only when no wrap-up is missing; after 2 turns it gives up and says so. With under 40,000 tokens of room it skips `wrap up` and says "no fresh handoff". Nothing compacts unless the person presses the button, except the before-the-cache-goes-cold setting the person chose.
5. **Settings go through whatsnext.** rightsize changes a whatsnext setting only with `config set --user <key> <value>`, after the person confirms. whatsnext checks the key and value against its schema, refuses an unknown key (exit 2) and never overwrites a user file that is not valid JSON.
6. **No shared files.** The only link is the command line and the session id.

## Why

Cost and cache timing live where the usage data is; the handoff structure lives where the project files are. One narrow contract keeps both plugins free to change.

## Trade-offs

- The contract is a shared interface: a field change in whatsnext must be announced to rightsize.
- Neither plugin can show the other's setting; the person sees each in its own place.
