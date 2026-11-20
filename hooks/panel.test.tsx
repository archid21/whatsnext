import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

import { panelRows, parseStatus, statusText } from './panel'

const PANE = {
  plugin: 'whatsnext',
  component: 'Pane',
  requestId: 'whatsnext-plan',
  props: {
    title: 'Plan',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

const TURN = { answer: 'ok', durationMs: 1, isAborted: false, turnId: 't', reason: 'end_turn' } as const

const STATUS = {
  current: { id: 'P-70', title: 'Plan side panel', status: 'in progress' },
  open: [
    { id: 'P-70', title: 'Plan side panel', status: 'in progress' },
    { id: 'P-89', title: 'Agent messages', status: 'open' },
    { id: 'P-80', title: 'Cross-machine claims', status: 'open', blocked_on: ['P-74'] },
  ],
  claims: [{ id: 'P-70', agent: 'claude-code', branch: 'p-70-panel', since_short: '19:29Z', stale: false }],
}

function engine(on: On, placed: boolean, status: unknown = STATUS) {
  mock.store(on)
  let calls = 0
  on('command.register', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: placed } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('turn.complete', () => ({ text: 'ok' }))
  on('ui.status', () => ({ value: undefined }))
  on('session.id', () => ({ value: 's1' }))
  on('session.cwd', () => ({ value: '/project' }))
  on('process.run', (_, e) => {
    if (e.argv.includes('status')) calls += 1

    return { value: { exitCode: 0, stdout: e.argv.includes('status') ? JSON.stringify(status) : '{}', stderr: '' } }
  })

  return () => calls
}

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the pane shows the active item, who has what and the open items (${surface})`, async ($, on) => {
    engine(on, true)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text', text: /^Active:/ }))?.text).toBe('Active: P-70 Plan side panel')
    expect((await ui.find({ type: 'Text', text: /claude-code/ }))?.text).toBe('P-70 claude-code on p-70-panel since 19:29Z')
    expect((await ui.find({ type: 'Text', text: /^Open items/ }))?.text).toBe('Open items: 3')
    expect(await ui.find({ type: 'Text', text: /P-89 Agent messages/ })).toBeDefined()
    await ui.unmount()
  })
}

test('the pane refreshes at each main-thread turn end, not after a subagent turn', async ($, on) => {
  const calls = engine(on, true)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const before = calls()
  await $.turn.complete(TURN)
  expect(calls()).toBe(before + 1)
  await $.turn.complete({ ...TURN, agentId: 'sub-1' })
  expect(calls()).toBe(before + 1)
})

test('an open message shows as one line with its sender and id, not its text', () => {
  const rows = panelRows(parseStatus(JSON.stringify({ ...STATUS, messages: [
    { id: 'M-1', kind: 'question', text: 'secret words', from: { agent: 'codex', item: 'P-88' } }] })), 80, 20)
  expect(rows.map(r => r.text)).toContain('Message: question from codex (P-88) · M-1')
  expect(rows.some(r => r.text.includes('secret words'))).toBe(false)
})

test('helpers: fallback line, missing fields and the overflow row', () => {
  expect(statusText(parseStatus(JSON.stringify(STATUS)))).toBe('P-70 active · 3 open')
  expect(statusText(parseStatus('{"handoff": null}'))).toBe('no active item · 0 open')
  expect(parseStatus('not json')).toBeUndefined()
  const many = { current: null, claims: [], open: Array.from({ length: 30 }, (_, i) => ({ id: `P-${i}`, title: 't' })) }
  const rows = panelRows(many, 40, 10)
  expect(rows.length).toBe(10)
  expect(rows[rows.length - 1].text).toBe('  … 24 more')
})
