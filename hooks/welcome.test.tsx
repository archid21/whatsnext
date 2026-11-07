import { expect, mock, test } from 'claude-code/testing'

const TABLE = 'Feature | What it does | How it works\nSet up your plan | ...\n'

test('/whatsnext-welcome is registered and answers with the table from the whatsnext command', async ($, on) => {
  mock.store(on)
  const ran: string[][] = []
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/project' }))
  on('process.run', (_, e) => {
    ran.push([...e.argv])

    return { value: { exitCode: 0, stdout: TABLE, stderr: '' } }
  })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const result = await $.command.run({ command: 'whatsnext-welcome', args: '' })
  expect(result.text).toBe(TABLE)
  expect(ran[0]?.slice(-1)).toEqual(['welcome'])
})

test('/whatsnext-welcome says so when the command fails, and points at the guide', async ($, on) => {
  mock.store(on)
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: '/project' }))
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: 'boom' } }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const result = await $.command.run({ command: 'whatsnext-welcome', args: '' })
  expect(result.text).toContain('Could not show the welcome table')
  expect(result.text).toContain('docs/GUIDE.md')
})
