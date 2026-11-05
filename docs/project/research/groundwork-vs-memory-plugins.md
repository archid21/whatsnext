# Groundwork (project-memory half) vs existing AI coding-agent memory tools

Date: 2026-11-04. Method: WebSearch (standard, one extended), GitHub pages and the GitHub API for stars and last push. Star counts are from 2026-11-04 to 2026-11-05 UTC.

## Verdict: build narrowly, for personal use. Do not invest in a public release.

The market is saturated. Memory (claude-mem, Mem0, Hindsight, Graphiti) has 25k to 113k stars each. Decision records, handoff notes and project rules each have a direct competitor or a built-in feature. The only thing nothing else does is bundle all four, in plain Markdown, with no dependency and no model call. That is a convenience for the owner, not a market gap. No evidence in this research supports a market for the bundle.

## What Groundwork is (from its README and ADR-0015, ADR-0038)

Numbered ADRs (new, check, recall, keyword reminder hook), ground rules with presets, first-run setup with `config set`, `init` with preview, import of existing repos, "Continue in a new chat" mod, `.env` guardrail, handoff note and wrap-up. Python 3.9+, standard library only (ADR-0015). Nothing is released (README: "Not released yet").

## Competitors

| Tool | Stores | Recall | Agents | Local / hosted | Maturity | ADRs / rules / handoff |
|---|---|---|---|---|---|---|
| Claude Code built-in: CLAUDE.md, `.claude/rules/`, auto memory | Your Markdown; Claude's own notes (per repo) | Loaded every session; auto memory first 200 lines or 25 KB; path-scoped rules on demand | Claude Code; reads `AGENTS.md` itself since v2.1.277 | Local files | Anthropic first party | Rules: yes, native. ADR: no. Handoff: no (issue #11455 still open, no Anthropic reply) |
| claude-mem | Tool observations and AI summaries (SQLite + Chroma) | Session-start injection; MCP search tools | Claude Code first; Codex, OpenCode, Cursor, others listed | Local worker (Bun); optional cloud sync | 113k stars, pushed 2026-11-05 | ADR: no. Rules: no. Handoff: a "human handoffs" view only |
| Mem0 | Extracted facts per user, session, agent | Hybrid semantic, keyword, entity search | Claude Code and Codex plugins; MCP | Hosted plugin (API key); self-host server; OpenMemory local | 68k stars, pushed 2026-11-04 | None of the three |
| Hindsight (Vectorize) | Facts, experiences, mental models in per-repo banks | Stop hook retains; UserPromptSubmit recalls; 4-way hybrid | Claude Code, Codex, Cursor CLI, Copilot CLI, opencode, Cline CLI | Self-host or cloud | 59k stars, pushed 2026-11-04 | None. "Curated knowledge pages" include in-flight work, not a handoff note |
| Letta (ex-MemGPT) | Agent memory in its own harness | Agent-managed | Its own harness (Letta Code) | Local server or Letta Cloud | 25k stars, pushed 2026-10-18 | Not applicable: a different harness, not a plugin |
| Serena | Markdown memories beside code tools (LSP) | Agent reads via MCP | Claude Code, Codex, Gemini CLI, Cursor, many | Local | 31k stars, pushed 2026-10-28 | Memory is secondary; pairs with `AGENTS.md`. License GPL-3.0 |
| Basic Memory | Markdown notes + SQLite index | Hybrid search; follows wikilinks | MCP: Claude Code, Codex, Cursor, others | Local free; cloud $15/month | 4.5k stars, pushed 2026-11-05; AGPL-3.0 | No ADR support, no rules; resume by notes only |
| Graphiti / Zep | Temporal knowledge graph | Hybrid + graph walk | Any (reference MCP server, no auth) | Self-host (needs Neo4j or FalkorDB); Zep hosted | 32.5k stars, pushed 2026-11-03 | None |
| Cline Memory Bank | Markdown files (`projectbrief`, `activeContext`, `progress`) | Rule makes Cline read them each task | Cline; ported to Cursor by convention | Local | Official Cline docs; pattern, not a product | Handoff-like (`activeContext`): yes. ADR: no |
| Cursor memory bank / Cursor Memories | Same pattern as Cline; Memories beta (2025) | `alwaysApply` rule | Cursor | Local | Community repos; official Memories page now redirects to Rules (one vendor source, unconfirmed) | Handoff-like only |
| Beads (now gastownhall/beads) | Dolt-backed issue graph | `bd ready`, `bd prime` | Claude Code, Codex, Cursor, Copilot, others | Local embedded Dolt; optional server | 28.5k stars, pushed 2026-11-05 | Tasks, not ADRs. `bd rules audit` checks `.claude/rules/` |
| GitHub Copilot Memory | Repo-scoped facts with citations | Validated against code before use | Copilot agent, code review, CLI | Hosted by GitHub | Public preview since 2026-01-15; paid plans | Memories expire after 28 days unused. No ADR, no handoff |
| **adr-kit** (rvdbreemen) | Numbered ADR files (MADR, Nygard) in `docs/adr/` | PreToolUse hook injects the governing ADR before edits; MCP server | Claude Code, Codex CLI, Copilot CLI certified; OpenCode, OMP | Local, MIT | 13 stars, 697 commits, v0.61.0, pushed 2026-10-24 | **ADR: yes, a superset of Groundwork** (numbering, supersede, lint, enforcement, `init` audit, `adr-migrate`). Rules: yes. Handoff: no |
| Bureau `bureau:adr` (xiaolai marketplace) | MADR pages, typed supersedes, trust tiers | Review queue; BUREAU.md imported by CLAUDE.md | Claude Code | Local, git-backed | 85 stars (marketplace repo) | ADR: yes. Rules: BUREAU.md. Handoff: no |
| ADR skills (everything-claude-code and others) | ADR files from a template | Skill on request | Claude Code via `skills add` | Local | ECC 297k stars, but the ADR skill itself was not found on its README | ADR: yes, thin |
| Handoff plugins: claude-handoff (REMvisual), claude-handoff-revive, cc-handoff, session-handoff | One Markdown handoff per session | Resume command or SessionStart hook | Claude Code only | Local | 70, 8, 0 stars; pushed Aug to Oct 2026 | Handoff: yes, the whole product |
| ECC Memory Vault (`ecc memory handoff`) | Portable Markdown memories | Handoff between harnesses | Many | Local | Inside a 297k-star repo | Handoff: yes, cross-harness |

Skipped by instruction: Context7 (not memory).

## Coverage of Groundwork's four jobs

| Job | Covered by | Gap left for Groundwork |
|---|---|---|
| Numbered decision records | adr-kit (stronger), Bureau, ADR skills | None. adr-kit has recall, supersede, import and enforcement. Groundwork's keyword reminder is weaker than adr-kit's pre-edit injection |
| Ground rules and presets | CLAUDE.md, `.claude/rules/`, `AGENTS.md` (native in Claude Code, Codex, Copilot, Cursor) | Presets only. Low value; a copied template does the same |
| Handoff note and wrap-up | 4+ handoff plugins, Cline `activeContext`, ECC | Multi-harness and committed in the repo. Most rivals are Claude Code only |
| Setup and import | adr-kit `init` and `adr-migrate`; native `/init` | Import of existing repos across all four jobs |

## Check of ADR-0004's competitor claims

Verified:
- claude-mem is a transcript observer with a worker process and `<private>` tags. Correct.
- Hindsight retains on Stop and recalls on UserPromptSubmit, per-repo banks. Correct.
- Beads uses Dolt, claims (`--claim`) and a ready queue. Correct.
- Codex hook event names and `/hooks` trust. Correct (developers page at learn.chatgpt.com).

Discrepancies:
1. **Beads URL is stale.** `steveyegge/beads` returns a 301 to `gastownhall/beads`. Update the link.
2. **Beads "binary, schema migrations and a server mode" overstates.** Default is embedded Dolt in `.beads/`; the server is optional. The Dolt and no-database trade-off still holds.
3. **cc-sessions is mislabeled.** The table lists it under "Handoff files". It is a DAIC workflow (edit-blocking plus task files with branches), 1.5k stars, last push 2025-12-17. It belongs under execution workflows or task pipelines. It has no handoff file.
4. **`.claude/handoff.md` is a proposal, not a tool.** It comes from issue #11455. The table lists it beside real tools.
5. **"60+ comments" on #11455 is not confirmed.** The page shows about 42. The issue is open, labeled `area:core` and `enhancement`, with no Anthropic reply. The themes ADR-0004 cites (verify, do not trust; host-side capture; collisions) are present.
6. **Cursor "hook support is disputed" is out of date.** A Cursor staff reply says `sessionStart` was fixed in v2.4, and `sessionEnd`, `preCompact` and `stop` exist. Output control on `beforeSubmitPrompt` is still reported inconsistent. Re-check before promising Tier 2.
7. **"claude-handoff" is ambiguous.** At least four repos use the name. REMvisual's has 70 stars, v2.1.5, Claude Code only, optional PreCompact hook, and a `/compact-handoff` mod. It does not need Beads.
8. **WorkWays could not be checked.** It is the owner's own tool and has no public page. Do not cite it as market evidence.
9. **Missing from the table:** adr-kit, Bureau, ECC Memory Vault, Succession and claude-code-handover (named in #11455), Mem0, Letta, Serena, Basic Memory, Graphiti, Copilot Memory, Cline Memory Bank.
10. **Claude Code now reads `AGENTS.md` natively (v2.1.277).** This weakens any "AGENTS.md is the one file every harness reads, so we manage it" selling point. It helps the plain-files approach.

## What Groundwork does that nothing else does

1. One install covering ADRs, handoff, rules and import, with zero dependencies (Python standard library, no daemon, no model call, no database).
2. Handoff note and ADRs that live as committed Markdown and work across Claude Code, Codex and others. Most handoff tools are Claude Code only.

Neither is a gap a buyer pays for. Both are design preferences.

## What to cut

1. Ground-rule presets. Native CLAUDE.md, `.claude/rules/` and `AGENTS.md` cover rules.
2. The keyword reminder hook for decisions. adr-kit injects the governing ADR before an edit, which is more precise. Either copy that idea or drop the hook and rely on `recall`.
3. Any ADR feature adr-kit already ships (supersede graph, lint, enforcement). Do not chase parity. Consider recommending adr-kit and keeping a thin `decision new/check` only.
4. The "Continue in a new chat" mod, unless used daily. Claude Code only; handoff plugins and `/compact-handoff` overlap.
5. Public packaging work: marketplace listing, glossary, extra presets, multi-harness adapters beyond Claude Code and Codex.

Keep: the handoff note, wrap-up, the `.env` guardrail (check that Claude Code permissions do not already cover it), and `init` with preview for the owner's own repos.

Stance: per the owner's rule, the conservative answer is not to market this as a new product. Stars of 13 for the closest ADR rival and 0 to 70 for handoff plugins show the narrow market is small even before competition.

## Sources

- https://code.claude.com/docs/en/memory
- https://github.com/anthropics/claude-code/issues/11455
- https://github.com/thedotmack/claude-mem
- https://github.com/mem0ai/mem0 and https://docs.mem0.ai/integrations/claude-code
- https://github.com/vectorize-io/hindsight and https://hindsight.vectorize.io/sdks/integrations/claude-code
- https://github.com/letta-ai/letta
- https://github.com/oraios/serena
- https://github.com/basicmachines-co/basic-memory
- https://github.com/getzep/graphiti
- https://docs.cline.bot/features/memory-bank.md
- https://supermemory.ai/blog/cursor-memory-via-mcp/ and https://forum.cursor.com/t/unknown-hook-type-sessionstart/149566
- https://github.com/gastownhall/beads (from https://github.com/steveyegge/beads)
- https://docs.github.com/en/copilot/concepts/agents/copilot-memory and https://github.blog/changelog/2026-01-15-agentic-memory-for-github-copilot-is-in-public-preview/
- https://github.com/rvdbreemen/adr-kit
- https://github.com/xiaolai/claude-plugin-marketplace
- https://github.com/affaan-m/everything-claude-code
- https://github.com/GWUDCAP/cc-sessions
- https://github.com/REMvisual/claude-handoff, https://github.com/sofumel/claude-handoff-revive, https://github.com/rhuss/cc-handoff
- https://learn.chatgpt.com/docs/hooks
- Local: Groundwork `release` README.md; `master` docs/decisions/ADR-0015, ADR-0038; whatsnext docs/decisions/ADR-0004-resume-contract.md
