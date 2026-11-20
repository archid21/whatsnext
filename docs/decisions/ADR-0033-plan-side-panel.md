# ADR-0033: Plan side panel: a Claude Code pane fed by `status --json`

- **Date:** 2026-11-20T19:29Z
- **Status:** accepted (user), 2026-11-20

Amends ADR-0001 ("Not in this release" lists a checklist pane). Builds on ADR-0017 (Codex and Claude Code share one execution contract) and ADR-0020 (session-aware claims).

## Context

P-70 asks for a panel beside the chat that shows the open items, the active item and who has what, and updates at each turn end. ADR-0001 excluded "a checklist pane" until a new decision was made. This is that decision.

What exists today:

- **Claude Code mods** can open a pane with `$.ui.open({id, title})` and draw it from `on('ui.render', {component: 'Pane', requestId: id}, ...)`. A pane the person did not open with a command is placed only at 144 columns or more (110 if opened by a command). `$.ui.open` returns `{isPlaced}`. `$.ui.status(text)` shows one line anywhere.
- **`hooks/register.tsx`** already handles `turn.complete` (main thread only, `!e.agentId`) and calls `$.ui.invalidate('ui.render')`.
- **`status --json`** returns `current`, `ready` (limit 3), `recommended`, `message`, `handoff`, `warnings`, `errors`. `current` is one item object (id, title, section, status, done_means, evidence, claim, next_action, progress_file and more). Its `claim` is `{agent, branch, session, worktree, since, sibling_worktree, since_short, idle_since, idle_short, stale}`, or null when unclaimed. `ready` items carry the same item shape.
- **`plan list --json`** returns `{items: [...]}` with every item and its `claim`, but not the `current`, `ready` or handoff data. A panel would need two commands to show the plan and the active item together.

## Decision

1. **The pane opens automatically at session start.** When it is not placed (`isPlaced` false: narrow terminal or no surface), the mod falls back to one `$.ui.status` line such as `P-70 active · 3 ready`, and a slash command opens the full pane on request. Opened by that command, the pane needs only 110 columns.
2. **One data source: extend `status --json` with two new keys.**
   - `open`: every item that is not done, in plan order, with the same item shape as `current` and `ready`.
   - `claims`: a list of `{id, agent, branch, session, since, since_short, idle_short, stale}` for every claimed item, so the panel shows who has what without reading `open` twice. The values are the existing `claim` fields; no new data is collected.
   The existing keys stay unchanged, so current readers keep working. The panel and other tools read one command. The panel shells out to `python3 skills/whatsnext/scripts/whatsnext.py status --json`. It makes no model call (ADR-0001 rule 4).
3. **The panel refreshes on `turn.complete` (main thread only) and on `session.start`.** The existing `turn.complete` handler already calls `$.ui.invalidate('ui.render')`; the render step re-runs the command. Subagent turns (`e.agentId` set) do not refresh it.
4. **Claude Code only.** Codex has no pane surface and stays unchanged. The new `status --json` keys are harness-neutral, so Codex users and scripts can read them.
5. **This amends ADR-0001.** The "checklist pane" entry leaves its "Not in this release" list, once this ADR is accepted. ADR-0001 itself is not edited until then.

## Why

- A pane beside the chat shows the plan without a command, so the person sees the active item and claims without asking.
- One extended command gives the panel, scripts and Codex the same data; a second command and a second shape would drift.
- Refreshing at turn end matches the done means ("updates at each turn end") and reuses the existing `turn.complete` hook. A timer would need a background process, which ADR-0001 rule 5 rules out.
- The status line fallback keeps the signal on narrow terminals, where a pane is not placed.
- Shelling out to the script keeps one source of truth and no model cost.

## Trade-offs and risks

- Each refresh starts a Python process. Cost is small per turn but nonzero; a slow or failing call must not block the turn, so the render step needs a timeout and a stale-data fallback.
- Automatic placement needs 144 columns; most terminals will see only the status line until the person runs the open command.
- `status --json` grows. Large plans make a larger payload on every refresh; `open` may need a cap, or a flag that returns it only on request.
- Two new keys are a public output contract; renaming them later breaks readers.
- The panel shows plan state as of the last turn end, not live changes made by another session in between.
- Claude Code mod APIs (`$.ui.open`, `ui.render`) may change; the mod is the only code that depends on them.
