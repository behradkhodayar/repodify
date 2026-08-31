/** Dropdown freshness, e.g. "latest: 3 days ago". */
export function latestLabel(unix: number | null | undefined, now = Date.now()): string | null {
  if (unix == null || unix <= 0) return null
  const secs = Math.max(0, Math.round(now / 1000 - unix))
  if (secs < 45) return 'latest: just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `latest: ${mins} minute${mins === 1 ? '' : 's'} ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `latest: ${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `latest: ${days} day${days === 1 ? '' : 's'} ago`
  const months = Math.round(days / 30)
  if (months < 12) return `latest: ${months} month${months === 1 ? '' : 's'} ago`
  const years = Math.round(months / 12)
  return `latest: ${years} year${years === 1 ? '' : 's'} ago`
}

/** Compact relative time, e.g. "just now", "5m ago", "3d ago". */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const secs = Math.round((Date.now() - then) / 1000)
  if (secs < 45) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

/** Short, human-scannable job id (first segment of a hash/uuid). */
export function shortId(id: string): string {
  return id.replace(/-/g, '').slice(0, 8)
}

/** Human label for a job status (e.g. "awaiting_review" -> "Awaiting review"). */
export function statusLabel(status: string): string {
  const s = status.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const ACTIVE = new Set(['queued', 'running', 'awaiting_review'])
export function isActive(status: string): boolean {
  return ACTIVE.has(status)
}

/** Pipeline stages in execution order. `list` is unused (selection happens at create). */
export const PIPELINE_STAGES = [
  'resolve',
  'download',
  'transcribe',
  'diarize',
  'summarize',
  'arc',
  'script',
  'tts',
  'assemble',
] as const

export type PipelineStage = (typeof PIPELINE_STAGES)[number]

/** First whole-number percent in `text`, or null if missing / >100. */
export function parsePercent(text: string | null | undefined): number | null {
  if (!text) return null
  const m = text.match(/\b(\d{1,3})%/)
  if (!m) return null
  const n = Number(m[1])
  return n <= 100 ? n : null
}

/** Compact duration between two instants, e.g. `12s`, `1m`, `1m 03s`. */
export function elapsedLabel(
  fromIso: string | null | undefined,
  toIso?: string | null,
  now = Date.now(),
): string {
  if (!fromIso) return ''
  const from = new Date(fromIso).getTime()
  const to = toIso ? new Date(toIso).getTime() : now
  if (Number.isNaN(from) || Number.isNaN(to) || to < from) return ''
  const secs = Math.round((to - from) / 1000)
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return s ? `${m}m ${String(s).padStart(2, '0')}s` : `${m}m`
}

/** Catalog voice label with an explicit gender tag, e.g. `Heart (female)`. */
export function stockVoiceLabel(name: string, gender: string | null | undefined): string {
  return gender ? `${name} (${gender})` : name
}
