# Handoff
Session: eb5f8678-6344-411d-aaa7-46a0f7788aef
Task: none
Written: 2026-11-10T08:10Z
Branch: p-32-next-shows-handoff

## Goal
Ship the GitHub star ask in whatsnext (done, released as 0.3.1) and get the matching ask into rightsize.

## Next action
Restart Claude Code so 0.3.1 loads, then say "what's next?" and start P-57: `python3 skills/whatsnext/scripts/whatsnext.py plan start P-57 --agent claude-code`.
Verify: `python3 skills/whatsnext/scripts/whatsnext.py status` shows P-57 as current.
If it fails: run `git status` and `plan check`; another session may hold the item.

## State
State on Tue 2026-11-10 12:10 AM PST (Pacific): whatsnext 0.3.1 released. main = e5a7e3d on GitHub, tag v0.3.1, GitHub Release "whatsnext 0.3.1" is Latest; installed plugin updated 0.3.0 -> 0.3.1 (restart needed). Last checks: 586 Python tests OK in 424 s, 58 hook tests pass, `claude plugin validate` passes. Star ask checked live in ~/scratch/startest: automatic ask, Next tip path, Star on GitHub, thanks line. Backup in Google Drive: whatsnext-backup-20261110.tar.gz.

## What changed
413e6ec star ask: hooks/star.ts, hooks/star.test.tsx, hooks/tips.ts, hooks/register.tsx, docs/GUIDE.md, ADR-0021
a7fc32f, 1898a83 docs/project/PLAN.md: P-65 done* with evidence; P-66 added
be6bf2a hooks/register.tsx: Next tip asks GitHub before naming repos
e5a7e3d Release 0.3.1: versions, docs/FEATURES.md Star ask row, README New in 0.3.1

## Decisions
ADR-0021 accepted (docs/decisions/ADR-0021-github-star-ask.md): star ask is a tip, not a slash command; once after the first verified done; shared with rightsize via ~/.config/archid21/stars.json. Release as 0.3.1 (user choice). P-65 closed with --evidence to skip an 11-minute rerun (user choice).

## Constraints
Local only: ask before any push. Do not commit the files that were here before this session: docs/project/handoffs/*.md (untracked), docs/project/progress/journal/P-52.md, tsconfig.json. Keep rightsize's plugins/rightsize/hooks/star.ts in step with hooks/star.ts. Do not edit ~/Projects/rightsize while another session has uncommitted work there.

## Open questions and blockers
rightsize welcome table breaks in the CLI: $.ui.log draws one line per call, so newlines show as � and the 79-column table wraps. Fix not started; another session has that code open (plugins/rightsize/hooks/welcome.ts). rightsize star ask is uncommitted in ~/Projects/rightsize and has no band ask yet.

## Dead ends
`plan done P-65 --verify "<both suites joined with &&>"`: refused, matches no saved check. Test sessions started from this chat's `!` commands opened in ~/Projects/whatsnext, not ~/scratch/startest; use `cd ~/scratch/startest && claude --plugin-dir ~/Projects/whatsnext`.
