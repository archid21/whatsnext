import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'whatsnext',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 6,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 5 },
    view: {},
  },
} as const

const messages = [{ role: 'user', text: 'a summary', toolUses: [] }] as const
// Nothing draws beneath the plugin in a test: this hook stands for the engine's own, empty band.
function engine(on: On, entries?: Record<string, unknown>) {
  mock.store(on, entries)
  on('session.compact', () => ({ messages }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>engine</Text>
  })
}

const compact = { trigger: 'manual', messages } as const

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the band shows one tip with two buttons, then Next tip and Stop tips work (${surface})`, async ($, on) => {
    engine(on)

    // Nothing shows before a tip applies.
    let ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /save this session/ })).toBeUndefined()
    await ui.unmount()

    await $.session.compact(compact)
    ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /save this session/ })).toBeDefined()
    expect(await ui.find({ type: 'Button', label: 'Next tip' })).toBeDefined()
    expect(await ui.find({ type: 'Button', label: 'Stop tips' })).toBeDefined()
    await ui.unmount()

    // Only one tip at a time: a second offer while one shows changes nothing.
    await $.session.compact(compact)
    ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /save this session/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /pick the next piece/ })).toBeUndefined()

    // Next tip: the shown tip is marked seen and the next one shows.
    await $.ui.press({ plugin: 'whatsnext', key: 'next', surface })
    await ui.unmount()
    ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: /save this session/ })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /pick the next piece/ })).toBeDefined()

    // Stop tips: the band never shows again, in this session or a later one.
    await $.ui.press({ plugin: 'whatsnext', key: 'stop', surface })
    await ui.unmount()
    ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Button', label: 'Next tip' })).toBeUndefined()
    await ui.unmount()
  })
}

test('the band yields while a survey is up or a turn is running', async ($, on) => {
  engine(on)
  await $.session.compact(compact)

  for (const props of [{ ...BAND.props, hasSurvey: true }, { ...BAND.props, isWorking: true }]) {
    const ui = await $.ui.mount({ ...BAND, props, surface: 'terminal' })
    expect(await ui.find({ type: 'Button', label: 'Next tip' })).toBeUndefined()
    await ui.unmount()
  }

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Button', label: 'Next tip' })).toBeDefined()
  await ui.unmount()
})

test('a stored tipsOff keeps the band hidden in a new session', async ($, on) => {
  engine(on, { tips: { tipsOff: true, seen: [] } })
  await $.session.compact(compact)

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Button', label: 'Next tip' })).toBeUndefined()
  await ui.unmount()
})
