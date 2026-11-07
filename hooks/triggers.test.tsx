import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'whatsnext',
  component: 'AbovePrompt',
  surface: 'terminal',
  props: { hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 100, scroll: { offset: 0, bodyRows: 5 }, view: {} },
} as const

const COMPACT = { command: 'compact', args: '' } as const

type World = { files?: Record<string, string>; stored?: Record<string, unknown> }

// What sits beneath the plugin in a test: the engine's drawing, a compaction, a turn end, a Bash tool and a folder.
function world(on: On, { files = {}, stored }: World = {}) {
  mock.store(on, stored)
  on('command.run', () => ({ text: 'Compacted.' }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: { stdout: 'Marked P-13 done. Verified: true passed in 1.0 s.', stderr: '' } }))
  on('fs.list', () => {
    const names = Object.keys(files)
    if (names.length === 0) throw new Error('ENOENT')

    return { value: names.map(name => ({ name, kind: 'file' })) }
  })
  on('fs.read', (_, e) => ({ value: files[String(e.path).split('/').pop() ?? ''] ?? '' }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })
}

async function band($: any, text: RegExp) {
  const ui = await $.ui.mount(BAND)
  const found = (await ui.find({ type: 'Button', label: 'Next tip' })) !== undefined && (await ui.find({ type: 'Text', text })) !== undefined
  await ui.unmount()

  return found
}

const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const

test('wrap up shows after a compact', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' } })
  expect(await band($, /save this session/)).toBe(false)
  await $.command.run(COMPACT)
  expect(await band($, /save this session/)).toBe(true)
})

test('wrap up shows after a long session, not before', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' } })
  for (let i = 0; i < 19; i++) await $.turn.complete(TURN)
  expect(await band($, /save this session/)).toBe(false)
  await $.turn.complete(TURN)
  expect(await band($, /save this session/)).toBe(true)
})

test("what's next shows when no task is active, after the first turn and never at startup", async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** done', 'P-2.md': '- **State:** parked' } })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(await band($, /pick the next piece/)).toBe(false)
  await $.turn.complete(TURN)
  expect(await band($, /pick the next piece/)).toBe(true)
})

test("what's next stays quiet when a task is active or there is no progress folder", async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' } })
  await $.turn.complete(TURN)
  expect(await band($, /pick the next piece/)).toBe(false)
})

test("what's next stays quiet when there is no progress folder", async ($, on) => {
  world(on)
  await $.turn.complete(TURN)
  expect(await band($, /pick the next piece/)).toBe(false)
})

test('mark done shows after a plan item passes its command, not after other commands', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' } })
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  expect(await band($, /close a plan item/)).toBe(false)
  await $.tool.call({ tool: 'Bash', command: 'python3 whatsnext.py plan done P-13 --verify "true"' })
  expect(await band($, /close a plan item/)).toBe(true)
})

test('a tip never shows twice in one session or after it was seen', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' } })
  await $.command.run(COMPACT)
  const ui = await $.ui.mount(BAND)
  await $.ui.press({ plugin: 'whatsnext', key: 'next', surface: 'terminal' })
  await ui.unmount()
  // Another compact in the same session does not bring the save tip back.
  await $.command.run(COMPACT)
  expect(await band($, /save this session/)).toBe(false)
})

test('a tip stored as seen does not show in a new session', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' }, stored: { tips: { tipsOff: false, seen: ['save'] } } })
  await $.command.run(COMPACT)
  expect(await band($, /save this session/)).toBe(false)
})

test('/whatsnext-tips is registered, clears tipsOff and the seen list, and links to the guide', async ($, on) => {
  world(on, { files: { 'P-1.md': '- **State:** active' }, stored: { tips: { tipsOff: true, seen: ['save', 'pick'] } } })
  const registered: string[] = []
  on('command.register', (_, e) => {
    registered.push(e.name)

    return { value: { command: e.name } }
  })

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(registered).toEqual(['whatsnext-tips'])

  // Stopped and seen: nothing shows.
  await $.command.run(COMPACT)
  expect(await band($, /save this session/)).toBe(false)

  const { text } = await $.command.run({ command: 'whatsnext-tips' })
  expect(text).toContain('docs/GUIDE.md')

  // Back on, nothing seen: the save tip shows again.
  await $.command.run(COMPACT)
  expect(await band($, /save this session/)).toBe(true)
})
