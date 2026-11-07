import type { EngineInterface, Register } from 'claude-code'

import { IDLE_MS, WRAP_UP, minTokens, saveTipKind, skipReason, type IdleFacts } from './idle'
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
    autoCompactEnabledSetting: await $.settings.read({ key: 'autoCompactEnabled' }),
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
  if (hasCheckedTask) return
  hasCheckedTask = true
  if ((await hasActiveTask($)) === false) await offer($, 'pick')
}

async function restart($: EngineInterface) {
  await restartTips($)
  current = undefined
  shown.clear()
  turns = 0
  hasCheckedTask = false
  $.ui.invalidate('ui.render')
}

async function advance($: EngineInterface, tip: Tip) {
  const state = await markSeen($, tip.id)
  current = nextTip(state.seen, tip.id)
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
      await afterTurn($)
    }

    return result
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    const isVerifiedDone = /whatsnext\.py"?\s+plan\s+done\b/.test(e.command) && /--verify\b/.test(e.command)
    if (isVerifiedDone && !result.deny && !result.isError && /Marked \S+ done/.test(JSON.stringify(result.result))) {
      await offer($, 'done')
    }

    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.props.isWorking) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    if (!current) {
      if (notice === undefined) return next(e)

      return (
        <Box>
          <Text>{notice}</Text>
        </Box>
      )
    }
    const tip = current
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
