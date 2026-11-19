# ADR-0031: one rigor setting for light, standard or strict rules

- **Date:** 2026-11-18T23:00Z
- **Status:** accepted (user), 2026-11-18

For P-92. Builds on the layered settings (config.py).

## Context

whatsnext adds rules: a guard on hand-ticked items, a drift note, a branch question at start. Some people want all of them; some want only the plan and the resume note. Today each rule is its own switch, so asking for "fewer rules" means knowing every key.

## Decision

1. A setting `rigor` with the values `light`, `standard` (the default) and `strict`.
2. The preset is a layer above the built-in defaults and below every file layer (user, project, local). A key set by hand in any file still wins. The highest file layer that sets `rigor` picks the preset.
3. `config show` names the source of each value the preset set as `preset: <name>`.
4. The presets, using only switches that exist today:

| Switch | light | standard | strict |
|---|---|---|---|
| plan.tickGuard | off | warn | deny |
| plan.driftNote | off | on | on |
| plan.branchOnStart | stay | ask | branch |
| plan.concurrentStart | stay | ask | worktree |
| plan.reuseRunMax | 60m | 60m | 15m |

5. `standard` sets nothing, so a project that never sets `rigor` behaves as before.

## Consequences

- One line, `config set --user rigor light`, turns the gates off.
- Review on every item and a warning for handoffs without `Check:` lines are not part of it: they need new settings first.
