import type { EngineInterface, Register } from 'claude-code'

import { CONTINUE, newSessionPrompt, terminalNotice, writtenSince } from './newchat'
import { IDLE_MS, WRAP_UP, minTokens, saveTipKind, skipReason, type IdleFacts } from './idle'
import { ME, REPOS, SHARED_PATH, askText, blockedByClaim, parseShared, readStarCheck, reposToAsk, type Shared } from './star'
import { GUIDE, TIPS, loadState, markSeen, nextTip, restartTips, stopTips, type Tip } from './tips'

// whatsnext tips band (P-36). One tip shows above the prompt, with Next tip and Stop tips.
// Which tip, and when, is decided by `offer` (P-37 adds the triggers). The band yields to a survey and to a
// running turn. The seen list and tipsOff live in `$.store`; what is on screen now lives in this module.
let current: Tip | undefined
let notice: string | undefined // one line after Turn on, until the next prompt
const shown = new Set<string>() // a tip shows once per session, even if it was not marked seen
let turns = 0
let hasCheckedTask = false
const LONG_SESSION_TURNS = 20
const PROGRESS_FOLDER = 'docs/project/progress'

// Idle wrap-up (P-40, ADR-0016). A timer starts at the end of each main-thread turn and stops when any prompt is
// submitted. When it runs out, `wrap up` is submitted once, if the whatsnext check and Claude Code's settings agree.
// After that no timer starts until the person sends a prompt of their own.
let idleTimer: { cancel: () => void } | undefined
let askedThisPeriod = false
const SCRIPT = 'skills/whatsnext/scripts/whatsnext.py'

// Start fresh after a wrap-up (P-67, ADR-0024). `wrapAskedAt` is when this session's `wrap up` was submitted; when
// that turn ends with the handoff note written, the band offers New session and Clear and continue until a prompt.
let wrapAskedAt: number | undefined
let afterWrap = false

// GitHub star ask (P-65, ADR-0021). `star` in `$.store` says a verified done has happened (the milestone). The shared
// file (./star.ts) says whether rightsize is installed, what is starred, and whether the person answered.
const STAR_KEY = 'star'
let starRepos: string[] | undefined // the repos the star tip names while it shows
let starTried = false // the automatic ask runs its checks at most once per session

async function sharedPath($: EngineInterface) {
  const home = await $.env.get('HOME')

  return home ? `${home}/${SHARED_PATH}` : undefined
}

async function readShared($: EngineInterface): Promise<Shared> {
  const path = await sharedPath($)
  if (!path) return parseShared(undefined)
  try {
    return parseShared(await $.fs.read(path))
  } catch {
    return parseShared(undefined)
  }
}

// false when the file cannot be written: then no ask shows, because its answer could not be kept.
async function writeShared($: EngineInterface, shared: Shared) {
  const path = await sharedPath($)
  if (!path) return false
  try {
    await $.fs.write(path, `${JSON.stringify(shared, null, 2)}\n`)

    return true
  } catch {
    return false
  }
}

async function nowIso($: EngineInterface) {
  return new Date(await $.clock.now()).toISOString()
}

// Say this plugin is installed, so rightsize's ask can name it too.
async function noteInstalled($: EngineInterface) {
  try {
    const shared = await readShared($)
    if (shared.installed[ME]) return
    shared.installed[ME] = await nowIso($)
    await writeShared($, shared)
  } catch {
    // the other plugin's ask names only its own repo
  }
}

async function gh($: EngineInterface, args: string[]) {
  try {
    return await $.process.run(['gh', 'api', ...args], { cwd: await $.session.cwd(), timeoutMs: 15_000 })
  } catch {
    return undefined
  }
}

// Ask GitHub about each repo the tip would name, and note the starred ones in `shared`. false when GitHub cannot say
// for one of them (no gh, not signed in, no network).
async function checkStars($: EngineInterface, shared: Shared) {
  for (const repo of reposToAsk(shared)) {
    const check = readStarCheck(await gh($, [`user/starred/${repo}`]))
    if (check === 'unknown') return false
    if (check === 'starred') shared.starred[repo] = true
  }

  return true
}

// The automatic ask: tips on and star not seen, the person has not answered, rightsize has not claimed the ask in
// the last 7 days, GitHub says this repo is not starred. An unknown answer from GitHub skips it for this session.
async function offerStar($: EngineInterface) {
  const state = await loadState($)
  if (state.tipsOff || state.seen.includes('star')) return false
  const shared = await readShared($)
  if (shared.answered || blockedByClaim(shared, await $.clock.now())) return false
  if (!(await checkStars($, shared))) return false
  const repos = reposToAsk(shared)
  if (!repos.includes(REPOS[ME])) {
    await writeShared($, shared)
    await markSeen($, 'star')

    return false
  }
  shared.claim = { by: ME, at: await nowIso($) }
  if (!(await writeShared($, shared))) return false
  // Both plugins may claim at the same moment: the one whose claim stayed in the file asks.
  if ((await readShared($)).claim?.by !== ME) return false
  starRepos = repos

  return offer($, 'star')
}

async function maybeOfferStar($: EngineInterface) {
  if (starTried || current) return
  const earned = ((await $.store.get(STAR_KEY)) as { earned?: unknown } | undefined)?.earned === true
  if (!earned) return
  starTried = true
  try {
    await offerStar($)
  } catch {
    // no ask this session
  }
}

// Open a page in the person's browser: macOS `open`, then Linux `xdg-open`.
async function openPage($: EngineInterface, url: string) {
  for (const opener of ['open', 'xdg-open']) {
    try {
      if ((await $.process.run([opener, url], { timeoutMs: 10_000 })).exitCode === 0) return true
    } catch {
      // try the next one
    }
  }

  return false
}

// Star on GitHub: star each repo the tip names with the person's own `gh` sign-in. A repo that could not be starred
// opens in the browser, and the line names its link.
async function pressStar($: EngineInterface, tip: Tip) {
  const repos = starRepos ?? [REPOS[ME]]
  const failed: string[] = []
  const shared = await readShared($)
  for (const repo of repos) {
    const ran = await gh($, ['-X', 'PUT', `user/starred/${repo}`])
    if (ran?.exitCode === 0) shared.starred[repo] = true
    else failed.push(repo)
  }
  shared.answered = await nowIso($)
  await writeShared($, shared)
  await markSeen($, tip.id)
  current = undefined
  starRepos = undefined
  if (failed.length === 0) {
    notice = 'Thanks for the star!'
  } else {
    const links = failed.map(r => `https://github.com/${r}`)
    await openPage($, links[0])
    notice = `Could not star from here. Star it on GitHub: ${links.join(' ')}`
  }
  $.ui.invalidate('ui.render')
}

async function declineStar($: EngineInterface, tip: Tip) {
  const shared = await readShared($)
  shared.answered = await nowIso($)
  await writeShared($, shared)
  starRepos = undefined
  await declineTip($, tip)
}

// Show `id` if tips are on, it was not seen, and nothing else is showing. A plain function declaration at the top
// of the file, because the engine follows `$` only into those.
async function offer($: EngineInterface, id: string) {
  if (current || shown.has(id)) return false
  const state = await loadState($)
  const tip = TIPS.find(t => t.id === id)
  if (!tip || state.tipsOff || state.seen.includes(id)) return false
  current = tip
  shown.add(id)
  $.ui.invalidate('ui.render')

  return true
}

// True when a progress file says `State: active`, false when none does, undefined when there is no progress folder
// (whatsnext is not set up here, so no tip is offered).
async function hasActiveTask($: EngineInterface) {
  try {
    const files = (await $.fs.list(PROGRESS_FOLDER)).filter(f => f.name.endsWith('.md'))
    for (const file of files) {
      if (/^- \*\*State:\*\* active\b/m.test(await $.fs.read(`${PROGRESS_FOLDER}/${file.name}`))) return true
    }

    return false
  } catch {
    return undefined
  }
}

function disarmIdle() {
  idleTimer?.cancel()
  idleTimer = undefined
}

function armIdle($: EngineInterface) {
  disarmIdle()
  if (askedThisPeriod) return
  idleTimer = $.clock.after(IDLE_MS, () => {
    idleTimer = undefined
    void idleWrapUp($)
  })
}

// What the module can read about Claude Code: its two compact settings, the context size and the minimum.
async function idleFacts($: EngineInterface): Promise<IdleFacts> {
  const { context } = await $.session.usage({ breakdown: 'summary' })

  return {
    idleCompaction: await $.settings.read({ key: 'idleCompaction' }),
    isAutoCompactEnabled: context.breakdown?.isAutoCompactEnabled,
    tokens: context.tokens,
    minTokens: minTokens(await $.env.get('CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS')),
  }
}

// Run one whatsnext hook command and read its one JSON line. undefined on any failure.
async function whatsnextHook($: EngineInterface, event: string) {
  const cwd = await $.session.cwd()
  const ran = await $.process.run(['python3', `${$.plugin.root}/${SCRIPT}`, 'hook', event, '--agent', 'claude-code'], {
    cwd,
    stdin: JSON.stringify({ session_id: await $.session.id(), cwd }),
    timeoutMs: 10_000,
  })

  return ran.exitCode === 0 ? (JSON.parse(ran.stdout) as Record<string, unknown>) : undefined
}

// Any error means no `wrap up`: this is a convenience and must never break the session.
async function idleWrapUp($: EngineInterface) {
  try {
    if (askedThisPeriod) return
    if (skipReason(await idleFacts($))) return
    if ((await whatsnextHook($, 'idle-check'))?.fire !== true) return
    askedThisPeriod = true
    await Promise.resolve($.prompt.submit({ text: WRAP_UP })).catch(() => undefined)
  } catch {
    // no wrap up this time
  }
}

// The handoff note's path, as whatsnext resolves it (a setting or AGENTS.md can move it). undefined on any failure.
async function handoffPath($: EngineInterface) {
  const cwd = await $.session.cwd()
  const ran = await $.process.run(['python3', `${$.plugin.root}/${SCRIPT}`, 'status', '--json'], { cwd, timeoutMs: 10_000 })
  if (ran.exitCode !== 0) return undefined
  const path = (JSON.parse(ran.stdout) as { handoff?: { path?: unknown } }).handoff?.path

  return typeof path === 'string' && path ? (path.startsWith('/') ? path : `${cwd}/${path}`) : undefined
}

// At the end of the wrap-up turn: offer to start fresh when the note was written in it. Any error offers nothing.
async function checkWrapUp($: EngineInterface, askedAt: number) {
  try {
    const path = await handoffPath($)
    const stat = path ? await $.fs.stat(path) : undefined
    if (stat?.kind === 'file' && writtenSince(stat.mtimeMs, askedAt)) {
      afterWrap = true
      $.ui.invalidate('ui.render')
    }
  } catch {
    // no offer this time
  }
}

function hideWrapUp($: EngineInterface) {
  afterWrap = false
  $.ui.invalidate('ui.render')
}

// New session keeps this chat. The desktop app has a session tool only the agent can call, so the agent is asked,
// in the person's words (they pressed the button). A terminal cannot open a window: the band shows the command.
async function newSession($: EngineInterface, surface: string) {
  hideWrapUp($)
  if (surface === 'desktop') {
    await Promise.resolve($.prompt.submit({ text: newSessionPrompt(), asUser: true })).catch(() => undefined)
  } else {
    notice = terminalNotice()
    $.ui.invalidate('ui.render')
  }
}

// Clear and continue: `/clear` (the old chat stays in /resume), then the first prompt of the new chat.
async function clearAndContinue($: EngineInterface) {
  hideWrapUp($)
  try {
    await $.command.run({ command: 'clear', args: '' })
    await $.prompt.submit({ text: CONTINUE, asUser: true })
  } catch {
    notice = 'Could not clear this chat. Type /clear, then: ' + CONTINUE
    $.ui.invalidate('ui.render')
  }
}

// The save tip that fits (P-42): the opt-in tip when auto-compact is on and auto wrap-up is off, the manual tip when
// auto-compact is off, else the plain `save` tip. Any error falls back to the plain tip.
async function offerSave($: EngineInterface) {
  try {
    const kind = saveTipKind(await idleFacts($))
    if (kind === 'manual' && (await offer($, 'manual'))) return true
    if (kind === 'idle' && (await whatsnextHook($, 'idle-offer'))?.offer === true && (await offer($, 'idle'))) return true
  } catch {
    // the plain tip below
  }

  return offer($, 'save')
}

// Turn on auto wrap-up for this person (user settings), and say so.
async function turnOnIdle($: EngineInterface, tip: Tip) {
  let ok = false
  try {
    const ran = await $.process.run(
      ['python3', `${$.plugin.root}/${SCRIPT}`, 'config', 'set', '--user', 'wrapup.autoIdle', 'true'],
      { cwd: await $.session.cwd(), timeoutMs: 10_000 },
    )
    ok = ran.exitCode === 0
  } catch {
    ok = false
  }
  await markSeen($, tip.id)
  current = undefined
  notice = ok
    ? 'Auto wrap-up is on: after 45 idle minutes whatsnext will say "wrap up" for you, once. Turn it off: whatsnext config set --user wrapup.autoIdle false.'
    : 'Could not turn on auto wrap-up. Run: python3 <plugin>/skills/whatsnext/scripts/whatsnext.py config set --user wrapup.autoIdle true'
  $.ui.invalidate('ui.render')
}

async function declineTip($: EngineInterface, tip: Tip) {
  await markSeen($, tip.id)
  current = undefined
  $.ui.invalidate('ui.render')
}

async function afterTurn($: EngineInterface) {
  turns += 1
  if (turns >= LONG_SESSION_TURNS && (await offerSave($))) return
  if (!hasCheckedTask) {
    hasCheckedTask = true
    if ((await hasActiveTask($)) === false && (await offer($, 'pick'))) return
  }
  await maybeOfferStar($)
}

async function restart($: EngineInterface) {
  await restartTips($)
  current = undefined
  shown.clear()
  turns = 0
  hasCheckedTask = false
  starTried = false
  starRepos = undefined
  $.ui.invalidate('ui.render')
}

// Next tip. When the walk lands on the star tip, GitHub is asked first, as for the automatic ask: the tip names only
// repos not starred, and is skipped once this repo is starred. When GitHub cannot say, the tip names the repos the
// shared file does not list as starred (the person chose to walk the tips).
async function advance($: EngineInterface, tip: Tip) {
  const state = await markSeen($, tip.id)
  current = nextTip(state.seen, tip.id)
  if (current?.id === 'star') {
    try {
      const shared = await readShared($)
      if (await checkStars($, shared)) await writeShared($, shared)
      if (shared.starred[REPOS[ME]]) {
        await markSeen($, 'star')
        current = nextTip([...state.seen, 'star'], 'star')
      } else {
        starRepos = reposToAsk(shared)
      }
    } catch {
      starRepos = undefined
    }
  }
  $.ui.invalidate('ui.render')
}

async function stop($: EngineInterface) {
  await stopTips($)
  current = undefined
  $.ui.invalidate('ui.render')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'whatsnext-tips', description: 'Show the whatsnext tips again' })
    await $.command.register({ name: 'whatsnext-welcome', description: 'Show what whatsnext does, as a table' })
    await noteInstalled($)

    return next(e)
  })

  // The welcome table (P-44) comes from the Python side, which also shows it once after install.
  on('command.run', { command: 'whatsnext-welcome' }, async ($, e, next) => {
    try {
      const ran = await $.process.run(['python3', `${$.plugin.root}/${SCRIPT}`, 'welcome'], { cwd: await $.session.cwd(), timeoutMs: 10_000 })
      if (ran.exitCode === 0 && ran.stdout.trim()) return { text: ran.stdout }
    } catch {
      // the line below
    }

    return { text: `Could not show the welcome table. The guide has the same list: ${GUIDE}` }
  })

  on('command.run', { command: 'whatsnext-tips' }, async ($, e, next) => {
    await restart($)

    return { text: `whatsnext tips are on again. What each one does: ${GUIDE}` }
  })

  // A compact is marked by the command that runs it. `session.compact` and `classic.PostCompact` cannot be used:
  // in a real session the engine's security plugin runs first and skips this plugin's hooks on both (the debug log
  // says "bypassed by cc-plugin-sec-default"). An automatic compact is not seen; the long-session trigger covers it.
  on('command.run', { command: 'compact' }, async ($, e, next) => {
    const result = await next(e)
    await offerSave($)

    return result
  })

  // Any submitted prompt ends the idle wait. Only the person's own prompt (Enter, or the phone or web client) starts a
  // new idle period; a notification or the plugin's own `wrap up` does not.
  on('prompt.submit', async ($, e, next) => {
    disarmIdle()
    if (afterWrap) hideWrapUp($)
    if (typeof e.text === 'string' && e.text.trim() === WRAP_UP) wrapAskedAt = await $.clock.now()
    if (notice !== undefined) {
      notice = undefined
      $.ui.invalidate('ui.render')
    }
    // An absent origin is the person's own prompt (the engine stamps Enter as `composer`).
    const kind = e.origin?.kind
    if (kind === undefined || kind === 'composer' || kind === 'bridge') askedThisPeriod = false

    return next(e)
  })

  // Never at startup: the first turn's end is the earliest a tip can show, apart from a compact.
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (!e.agentId) {
      armIdle($)
      if (wrapAskedAt !== undefined) {
        const askedAt = wrapAskedAt
        wrapAskedAt = undefined
        await checkWrapUp($, askedAt)
      }
      await afterTurn($)
    }

    return result
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    const isVerifiedDone = /whatsnext\.py"?\s+plan\s+done\b/.test(e.command) && /--verify\b/.test(e.command)
    if (isVerifiedDone && !result.deny && !result.isError && /Marked \S+ done/.test(JSON.stringify(result.result))) {
      await offer($, 'done')
      await $.store.set(STAR_KEY, { earned: true }).catch(() => undefined)
    }

    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.props.isWorking) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    if (afterWrap) {
      const surface = e.surface
      return (
        <Box>
          <Text>Handoff written. Start fresh with it: </Text>
          <Button
            key="new-session"
            label="New session"
            onPress={() => newSession($, surface)}
          />
          <Button
            key="clear-continue"
            label="Clear and continue"
            onPress={() => clearAndContinue($)}
          />
          <Button
            key="not-now"
            label="Not now"
            onPress={() => hideWrapUp($)}
          />
        </Box>
      )
    }
    if (!current) {
      if (notice === undefined) return next(e)

      return (
        <Box>
          <Text>{notice}</Text>
        </Box>
      )
    }
    const tip = current
    if (tip.action === 'star') {
      return (
        <Box>
          <Text>
            {starRepos && starRepos.length > 0 ? askText(starRepos) : tip.text} <Text dimColor>{tip.link}</Text>{' '}
          </Text>
          <Button
            key="star"
            label="Star on GitHub"
            onPress={() => pressStar($, tip)}
          />
          <Button
            key="no-thanks"
            label="No thanks"
            onPress={() => declineStar($, tip)}
          />
        </Box>
      )
    }
    if (tip.action === 'turn-on-idle') {
      return (
        <Box>
          <Text>
            {tip.text} <Text dimColor>{tip.link}</Text>{' '}
          </Text>
          <Button
            key="turn-on"
            label="Turn on"
            onPress={() => turnOnIdle($, tip)}
          />
          <Button
            key="no-thanks"
            label="No thanks"
            onPress={() => declineTip($, tip)}
          />
        </Box>
      )
    }

    return (
      <Box>
        <Text>
          {tip.text} <Text dimColor>{tip.link}</Text>{' '}
        </Text>
        <Button
          key="next"
          label="Next tip"
          onPress={() => advance($, tip)}
        />
        <Button
          key="stop"
          label="Stop tips"
          onPress={() => stop($)}
        />
      </Box>
    )
  })
}
