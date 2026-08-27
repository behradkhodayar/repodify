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
