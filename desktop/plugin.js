import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  host,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  useQuery
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useMemo } from 'react'

const ID = 'pending-queue-monitor'
const PAGE_PATH = '/pending-monitor'
let rest = null

function formatAge(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}

function formatTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

function StatCard({ label, value }) {
  return jsxs('div', { className: 'flex min-w-32 flex-1 flex-col gap-1 rounded-md border border-(--ui-stroke-secondary) p-3', children: [
    jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: label }),
    jsx('div', { className: 'text-xl font-semibold text-(--ui-text-primary)', children: String(value) })
  ] })
}

function PendingPage() {
  const query = useQuery({
    queryKey: [ID, 'overview'],
    queryFn: () => rest('/overview'),
    refetchInterval: 30000
  })
  const data = query.data
  const rows = useMemo(() => data?.items || [], [data])
  if (query.isLoading) return jsx('div', { className: 'flex h-full items-center justify-center', children: jsx(GlyphSpinner, {}) })
  if (query.isError) return jsx('div', { className: 'flex h-full items-center justify-center p-6', children: jsx(ErrorState, { title: 'Pending monitor unavailable', description: 'The local backend could not be read. Try again after the plugin backend is mounted.', children: jsx(Button, { onClick: () => query.refetch(), children: 'Retry' }) }) })
  if (!data) return null
  const totals = data.totals
  return jsxs('div', { className: 'flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 text-sm', children: [
    jsxs('div', { className: 'flex items-center justify-between gap-3', children: [
      jsxs('div', { children: [jsx('h1', { className: 'text-lg font-semibold', children: 'Pending Monitor' }), jsx('p', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Read-only metadata from local pending queues' })] }),
      jsx(Button, { variant: 'ghost', onClick: () => query.refetch(), children: 'Refresh' })
    ] }),
    jsxs('div', { className: 'flex flex-wrap gap-3', children: [
      jsx(StatCard, { label: 'Pending Memory', value: totals.pending_memory }),
      jsx(StatCard, { label: 'Pending Skills', value: totals.pending_skills }),
      jsx(StatCard, { label: 'Total', value: totals.total }),
      jsx(StatCard, { label: 'Oldest waiting', value: formatAge(totals.oldest_age_seconds) })
    ] }),
    jsxs('div', { className: 'flex flex-col gap-2', children: [
      jsx('h2', { className: 'font-medium', children: 'By profile' }),
      jsx('div', { className: 'grid gap-2 md:grid-cols-2', children: data.profiles.map(profile => jsxs('div', { className: 'flex items-center justify-between rounded-md border border-(--ui-stroke-secondary) p-3', children: [jsx('span', { children: profile.profile }), jsxs('span', { className: 'flex gap-2 text-xs text-(--ui-text-tertiary)', children: [jsx(Badge, { children: `Memory ${profile.pending_memory}` }), jsx(Badge, { children: `Skills ${profile.pending_skills}` }), jsx('span', { children: `oldest ${formatAge(profile.oldest_age_seconds)}` })] })] }, profile.profile)) })
    ] }),
    jsxs('div', { className: 'flex flex-col gap-2', children: [jsx('h2', { className: 'font-medium', children: 'Age buckets' }), jsx('div', { className: 'flex flex-wrap gap-2', children: data.age_buckets.map(bucket => jsx(Badge, { children: `${bucket.label}: ${bucket.count}` }, bucket.label)) })] }),
    rows.length === 0 ? jsx(EmptyState, { title: 'Queue is empty', description: data.skipped ? `${data.skipped} unreadable file(s) skipped.` : 'No pending memory or skill writes were found.' }) : jsxs('div', { className: 'min-w-[960px] overflow-hidden rounded-md border border-(--ui-stroke-secondary)', children: [
      jsx('div', { className: 'grid grid-cols-[1.1fr_0.8fr_0.7fr_0.9fr_1.2fr_1fr_0.7fr] gap-3 border-b border-(--ui-stroke-secondary) px-3 py-2 text-xs text-(--ui-text-tertiary)', children: ['ID', 'Profile', 'Type', 'Action', 'Origin', 'Created', 'Age'].map(label => jsx('div', { children: label }, label)) }),
      rows.map(item => jsx('div', { className: 'grid grid-cols-[1.1fr_0.8fr_0.7fr_0.9fr_1.2fr_1fr_0.7fr] gap-3 border-b border-(--ui-stroke-secondary) px-3 py-2 text-xs last:border-b-0', children: [jsx('div', { className: 'truncate', children: item.id }), jsx('div', { children: item.profile }), jsx('div', { children: item.subsystem }), jsx('div', { children: item.action || '—' }), jsx('div', { className: 'truncate', children: item.origin || '—' }), jsx('div', { children: formatTime(item.created_at) }), jsx('div', { children: formatAge(item.age_seconds) })] }, `${item.profile}-${item.subsystem}-${item.id}`))
    ] }),
    data.skipped || data.truncated ? jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: `${data.skipped ? `${data.skipped} unreadable or malformed file(s) skipped. ` : ''}${data.truncated ? 'Results are truncated at 1,000 items.' : ''}` }) : null
  ] })
}

export default {
  id: ID,
  name: 'Pending Monitor',
  register(ctx) {
    rest = (path, opts) => ctx.rest(path, opts)
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: PAGE_PATH }, render: () => jsx(PendingPage, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PAGE_PATH, label: 'Pending Monitor', codicon: 'inbox' } },
      { id: 'open', area: PALETTE_AREA, data: { id: `${ID}.open`, label: 'Open Pending Monitor', keywords: ['pending', 'memory', 'skills', 'queue'], run: () => host.navigate(PAGE_PATH) } }
    ])
  }
}
