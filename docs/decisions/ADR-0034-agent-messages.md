# ADR-0034: Agent-to-agent messages: one file per message in the shared git folder, addressed to an agent, an item or the user

- **Date:** 2026-11-20T21:06Z
- **Status:** accepted (user), 2026-11-20

Builds on ADR-0020 (session-aware claims), ADR-0032 (fan-out: one session per item, each in its own worktree) and ADR-0033 (`status --json` feeds the plan pane). Idea from repo-context-skills.

## Context

With fan-out (ADR-0032), two sessions work side by side in separate worktrees. One may need to ask the other a question ("I need a field in `status --json`; will you add it?"), ask for a review, or answer. Today the user relays every such note between chats, or the clash shows only at merge.

The plan item names `docs/project/messages/`. A file there is in one worktree's working tree only: a session in another worktree does not see it until the branch is merged. That defeats the main use.

## Decision

1. **One file per message, written once, never edited.** JSON with `id` (`M-<UTC stamp>-<4 hex>`), `from` (agent, session, item), `to`, `kind` (`question`, `review`, `answer`, `note`), `text`, `written`, and `in_reply_to` (an answer's question id, else null). A reply is a new file, never an edit.
2. **Stored in the shared git folder:** `<git common dir>/whatsnext/messages/`. Every worktree of the repository on this machine sees the same folder, and nothing is committed. Cross-machine delivery waits for P-80.
3. **Addressed to an item, an agent or the user.** `to` is `P-NN` (whoever holds that item, now or later), `agent:<name>` (for example `agent:codex`), or `user`.
4. **Open until answered.** A message is open while no message has `in_reply_to` its id, or until `message close <id>` writes a `note` that closes it. Nothing is deleted.
5. **Commands:** `message send --to <to> --kind <kind> "<text>"`, `message list [--open] [--json]`, `message answer <id> "<text>"`, `message close <id>`. `list` defaults to the messages for this session: its claimed item, its agent name.
6. **`status --json` adds `messages`:** the open messages for this session's item and agent. The plan pane (ADR-0033) shows one line per open message.
7. **A message is data, never permission.** It is shown as quoted text from another agent. An agent never acts on a request in a message that needs the user's OK (push, delete, release, spend); it asks the user. SKILL.md says so.
8. **Size and pruning:** a text over 4,000 characters is refused. Closed or answered messages older than 30 days are pruned like other session state (ADR-0018).

## Why

- The shared git folder is the one place every worktree on this machine sees without a merge, and it keeps message noise out of commits.
- Write-once files need no locking: two agents never edit one file.
- Addressing an item, not a session, reaches whoever holds it, including the next session after a handoff.
- Status and the pane are where agents and the user already look.

## Trade-offs and risks

- Messages are not in git history and do not reach another machine or a fresh clone. P-80 can add a ref later.
- A message to an item nobody holds waits until someone starts it.
- Another agent's text enters the reader's context: a prompt-injection path. Rule 7 and quoting limit it; they do not remove it.
- This departs from the plan item's original `docs/project/messages/`; the plan line now names the shared git folder.
