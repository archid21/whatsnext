# ADR-0027: whatsnext works in any coding agent, in three support tiers

- **Date:** 2026-11-15T22:52Z
- **Status:** accepted (user), 2026-11-15

Amends ADR-0001 ("Not in this release": harnesses other than Claude Code and Codex, tracker adapters, cross-machine claims) and its rule 5 ("no background process"). Extends ADR-0017.

## Context

The plan, progress and handoff files are already readable by every agent. What differs per agent is how it learns the rules and when whatsnext gets to run. A check on 2026-11-15 found that most coding agents read `AGENTS.md` and load `SKILL.md` skills, that Gemini CLI and Cursor have hooks with their own event names, and that trackers (Beads, Task Master, Backlog.md) answer "what's next?" but have no proven check-off and no resume note. The hook facts for Cursor come from secondary sources and are not verified.

## Decision

1. **Three support tiers,** stated in the README for each agent:
   - **Files:** the agent reads and edits `PLAN.md`, progress files and `HANDOFF.md`. Every agent.
   - **Instructions:** the `AGENTS.md` block and the skill tell the agent to run `wn status` at start and to write the handoff on `wrap up`. No hooks. The agent pulls the resume note.
   - **Hooks:** a per-agent adapter maps the agent's hook events to five internal events (start, prompt, turn end, before compact, session end). The resume note, the journal and the compact text arrive unasked.
2. **The instructions tier must be enough alone.** Hook formats change without notice; an agent with no adapter, or a broken one, still gets the plan, the verified check-off and the handoff.
3. **One adapter table.** `install-hooks` takes an agent name. Each adapter is one small file plus fixtures. An unknown conversation format falls back to facts only (ADR-0017).
4. **An agent is "supported"** only after the live acceptance checklist passes for it and `doctor` reports its hooks. Until then the README says "experimental".
5. **Tracker sync is read-first.** whatsnext reads ready items from a tracker (Beads, GitHub Issues) and adds the verified check-off and the handoff. `PLAN.md` stays the source of truth for check-offs. Any network call is made by the user's own tool (`bd`, `gh`), never by whatsnext itself.
6. **Cross-machine claims** live on a git ref. whatsnext still never pushes; the user or their agent pushes the ref.
7. **MCP server.** A standard-library server that the agent starts per session and that wraps the existing commands is allowed. It is not a daemon: it ends with the session. It comes after tiers 2 and 3, for agents with no shell.

## Trade-offs

- Each adapter is upkeep: fixtures break when an agent changes its hook format.
- The instructions tier depends on the agent following text, so `plan check` stays the safety net.
- Tracker sync adds a second place where an item's state can differ from `PLAN.md`.
- MCP tool definitions use context in every session, even when unused.

## Plan items

P-74 to P-81.
