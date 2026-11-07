import type { EngineInterface, Register } from 'claude-code'

import { IDLE_MS, WRAP_UP, minTokens, skipReason } from './idle'
import { GUIDE, TIPS, loadState, markSeen, nextTip, restartTips, stopTips, type Tip } from './tips'

// whatsnext tips band (P-36). One tip shows above the prompt, with Next tip and Stop tips.
// Which tip, and when, is decided by `offer` (P-37 adds the triggers). The band yields to a survey and to a
// running turn. The seen list and tipsOff live in `$.store`; what is on screen now lives in this module.
let current: Tip | undefined
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

// Any error means no `wrap up`: this is a convenience and must never break the session.
async function idleWrapUp($: EngineInterface) {
  try {
    if (askedThisPeriod) return
    const { context } = await $.session.usage({ breakdown: 'summary' })
    const reason = skipReason({
      idleCompaction: await $.settings.read({ key: 'idleCompaction' }),
      autoCompactEnabledSetting: await $.settings.read({ key: 'autoCompactEnabled' }),
      isAutoCompactEnabled: context.breakdown?.isAutoCompactEnabled,
      tokens: context.tokens,
      minTokens: minTokens(await $.env.get('CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS')),
    })
    if (reason) return
    const cwd = await $.session.cwd()
    const ran = await $.process.run(['python3', `${$.plugin.root}/${SCRIPT}`, 'hook', 'idle-check', '--agent', 'claude-code'], {
      cwd,
      stdin: JSON.stringify({ session_id: await $.session.id(), cwd }),
      timeoutMs: 10_000,
    })
    if (ran.exitCode !== 0 || JSON.parse(ran.stdout).fire !== true) return
    askedThisPeriod = true
    await Promise.resolve($.prompt.submit({ text: WRAP_UP })).catch(() => undefined)
  } catch {
    // no wrap up this time
  }
}

async function afterTurn($: EngineInterface) {
  turns += 1
  if (turns >= LONG_SESSION_TURNS && (await offer($, 'save'))) return
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

    return next(e)
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
    await offer($, 'save')

    return result
  })

  // Any submitted prompt ends the idle wait. Only the person's own prompt (Enter, or the phone or web client) starts a
  // new idle period; a notification or the plugin's own `wrap up` does not.
  on('prompt.submit', async ($, e, next) => {
    disarmIdle()
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
    if (e.props.hasSurvey || e.props.isWorking || !current) return next(e)
    const tip = current
    const { Box, Button, Text } = $.ui.resolve(e)

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
