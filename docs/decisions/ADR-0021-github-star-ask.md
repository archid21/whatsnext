# ADR-0021: Ask once for a GitHub star in the tips band, shared with rightsize

- **Date:** 2026-11-10T06:45Z
- **Status:** accepted (user), 2026-11-10

Builds on the tips band (P-35 to P-37). Claude Code only. Modeled on t3code's star prompt (pingdotgg/t3code#27832, #28364, #29922).

## Decision

1. **The ask is a tip, not a command.** The `star` tip has two buttons: **Star on GitHub** and **No thanks**. It is the last tip in the **Next tip** walk, so a person who said no can find it later with `/whatsnext-tips`. **Stop tips** also stops it.
2. **When it is offered on its own:** at the end of a main-thread turn, after the first `plan done --verify` that passed (kept in `$.store` as `star.earned`). Never at startup, never while a turn runs, never while another tip shows. The checks run at most once per session.
3. **Only when it is wanted:** tips are on; the tip is not seen; the person has not answered; GitHub says the repo is not starred (`gh api user/starred/archid21/whatsnext`: exit 0 is starred, HTTP 404 is not). Any other answer (no `gh`, not signed in, no network) skips the ask for this session and saves nothing.
4. **One click:** **Star on GitHub** runs `gh api -X PUT user/starred/<repo>` with the person's own `gh` sign-in, and says "Thanks for the star!". If that fails, the repo page opens in the browser (`open`, then `xdg-open`) and the line gives the link. Nothing is starred without the click.
5. **Shared with rightsize.** Each plugin's `$.store` is private, so both read and write `~/.config/archid21/stars.json`:
   - `installed`: plugin name and first-seen time (UTC), written at session start.
   - `starred`: repos GitHub reported as starred, or that the person starred from the band.
   - `answered`: UTC time of **Star** or **No thanks**. After it, neither plugin asks on its own.
   - `claim`: the plugin showing the ask and when. A claim by the other plugin less than 7 days old blocks this plugin's ask. After writing its claim, a plugin reads the file again and asks only if its claim stayed.
6. **Both plugins installed:** one ask names both repos ("Finding whatsnext and rightsize useful?"), minus the ones already starred. **Star on GitHub** stars both. **No thanks** answers for both.
7. **A file that cannot be written means no ask.** An answer that cannot be kept would turn into a nag.

## Why

A star helps other people find the plugins. t3code's experience: an ask during focused work is closed unread; an ask during downtime, with a one-click star, gets read. Asking after a verified done means the person has seen whatsnext work.

## Not done

- No new ask after **No thanks**, not even after a release.
- A plugin installed after the person answered does not ask again. It can still be starred from the **Next tip** walk.
- Codex has no band, so it has no ask.

## rightsize

rightsize keeps a copy of `hooks/star.ts` with `ME = 'rightsize'` and the same file format and rules. A change to either copy must change the other.
