# ADR-0026: After a wrap-up, the band offers Compact here or a paste-in new session

- **Date:** 2026-11-11T15:09Z
- **Status:** accepted (user), 2026-11-11

Supersedes the button parts of ADR-0024 (New session via the agent, Clear and continue) and the `new_session_prompt` and `clear_command` use in ADR-0025. P-69.

## Context

A live test showed 3 clicks and a nested session. The desktop app counts a plugin's `asUser` prompt as the plugin's, so `start_session` with `user_asked` was refused and fell back to a proposal card, and the new session nested under the old one.

## Decision

1. **The band after a wrap-up** (the turn wrote the handoff note) shows **Compact here**, **New session** and **Not now**, until the person submits a prompt.
2. **Compact here** runs `/compact` in this session with whatsnext's compact text (`compact-instructions --json`, field `instructions`; the handoff is carried in). If that text cannot be read, a plain `/compact` runs and the PreCompact hook carries the handoff.
3. **New session** sends nothing to the model. The band shows "Paste this in a new session in this project to continue fresh:" and the continue prompt, with a **Copy** button (`$.ui.copy`). If the copy fails, the text stays shown and the band says so. In a terminal it shows the `claude "..."` command to run in a new terminal window in this folder instead.
4. **Not now** closes the band. Any prompt the person submits also closes it.
5. **rightsize's `wrap up`:** when the `wrap up` prompt has origin `{ kind: 'plugin', name: 'rightsize' }`, whatsnext shows no band; rightsize shows its own choice. The origin is read at prompt time.
6. **`fresh-instructions --json`** keeps all its keys. `new_session_prompt` and `clear_command` stay for compatibility but whatsnext no longer uses them; rightsize needs only `continue_prompt` and `terminal_command`.
7. The wrap-up reply tells the person to press Compact here or New session.
