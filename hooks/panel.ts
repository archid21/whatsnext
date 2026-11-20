// Plan side panel (P-70, ADR-0033). Pure helpers: turn `whatsnext status --json` into the pane's rows and the
// one-line fallback. register.tsx runs the command and draws; nothing here touches the engine.

export const PANE = 'whatsnext-plan'
export const PANE_TITLE = 'Plan'
export const PANE_COMMAND = 'whatsnext-plan'

type Claim = { id: string; agent?: string | null; branch?: string | null; since_short?: string | null; stale?: boolean }
type Item = { id: string; title?: string; status?: string; blocked_on?: unknown }
type Message = { id: string; kind?: string; to?: string; from?: { agent?: string; item?: string | null } }
export type PlanStatus = { current?: Item | null; open?: Item[]; claims?: Claim[]; messages?: Message[] }

export type Row = { text: string; bold?: boolean; dim?: boolean }

function short(text: string | undefined, max: number) {
  const t = (text ?? '').trim()

  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

// The status, read leniently: a missing or odd field reads as empty.
export function parseStatus(stdout: string): PlanStatus | undefined {
  try {
    const data = JSON.parse(stdout) as PlanStatus
    if (!data || typeof data !== 'object') return undefined

    return {
      current: data.current && typeof data.current.id === 'string' ? data.current : null,
      open: Array.isArray(data.open) ? data.open.filter(v => v && typeof v.id === 'string') : [],
      claims: Array.isArray(data.claims) ? data.claims.filter(c => c && typeof c.id === 'string') : [],
      messages: Array.isArray(data.messages) ? data.messages.filter(m => m && typeof m.id === 'string') : [],
    }
  } catch {
    return undefined
  }
}

// The pane: the active item first, then who has what, then every open item. `room` is the rows there are.
export function panelRows(s: PlanStatus | undefined, columns = 40, room = 20): Row[] {
  if (!s) return [{ text: 'No plan status yet.', dim: true }]
  const width = Math.max(20, columns)
  const rows: Row[] = []
  rows.push(s.current
    ? { text: `Active: ${s.current.id} ${short(s.current.title, width - 9 - s.current.id.length)}`, bold: true }
    : { text: 'Active: none', dim: true })
  const claims = s.claims ?? []
  rows.push({ text: claims.length ? 'Who has what' : 'Who has what: nobody', dim: !claims.length })
  for (const c of claims) {
    const who = [c.agent ?? 'unknown', c.branch ? `on ${c.branch}` : '', c.since_short ? `since ${c.since_short}` : '']
      .filter(Boolean).join(' ')
    rows.push({ text: short(`  ${c.id} ${who}${c.stale ? ' (stale)' : ''}`, width), dim: !!c.stale })
  }
  // Open messages for this session (ADR-0034): who sent what kind, never the text itself.
  for (const m of s.messages ?? []) {
    const from = [m.from?.agent ?? 'unknown', m.from?.item ? `(${m.from.item})` : ''].filter(Boolean).join(' ')
    rows.push({ text: short(`Message: ${m.kind ?? 'note'} from ${from} · ${m.id}`, width), bold: true })
  }
  const open = s.open ?? []
  rows.push({ text: `Open items: ${open.length}`, dim: !open.length })
  const left = Math.max(1, room - rows.length)
  const shown = open.length > left ? open.slice(0, left - 1) : open
  for (const v of shown) {
    const mark = v.id === s.current?.id ? '>' : v.blocked_on ? 'x' : ' '
    rows.push({ text: short(`${mark} ${v.id} ${v.title ?? ''}`, width), bold: v.id === s.current?.id, dim: !!v.blocked_on })
  }
  if (shown.length < open.length) rows.push({ text: `  … ${open.length - shown.length} more`, dim: true })

  return rows
}

// The status-line fallback when the pane is not placed: "P-70 active · 7 open".
export function statusText(s: PlanStatus | undefined) {
  if (!s) return undefined
  const open = (s.open ?? []).length

  return `${s.current ? `${s.current.id} active` : 'no active item'} · ${open} open`
}
