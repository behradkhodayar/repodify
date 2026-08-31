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
export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—'
  const then = parseInstant(iso)
  if (then == null) return '—'
  const secs = Math.round((now - then) / 1000)
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

/** Milliseconds since epoch. Naive ISO (no Z / offset) is UTC — our API stores UTC. */
const TZ_SUFFIX = /(?:[zZ]|[+-]\d{2}:?\d{2})$/

export function parseInstant(iso: string | null | undefined): number | null {
  if (!iso) return null
  const trimmed = iso.trim()
  if (!trimmed) return null
  const normalized = TZ_SUFFIX.test(trimmed) ? trimmed : `${trimmed}Z`
  const ms = Date.parse(normalized)
  return Number.isNaN(ms) ? null : ms
}

function formatElapsedMs(ms: number): string {
  const secs = Math.round(ms / 1000)
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return s ? `${m}m ${String(s).padStart(2, '0')}s` : `${m}m`
}

/** Compact duration between two instants, e.g. `12s`, `1m`, `1m 03s`. */
export function elapsedLabel(
  fromIso: string | null | undefined,
  toIso?: string | null,
  now = Date.now(),
): string {
  const from = parseInstant(fromIso)
  if (from == null) return ''
  const to = toIso ? parseInstant(toIso) : now
  if (to == null || to < from) return ''
  return formatElapsedMs(to - from)
}

type StageTimes = {
  stage: string
  started_at: string | null
  finished_at: string | null
}

/**
 * Wall-clock length of one job: first Resolve start → Assemble finish (or now).
 * Does not sum per-stage times or look at other jobs.
 */
export function pipelineElapsed(stages: readonly StageTimes[], now = Date.now()): string {
  const resolveStarts = stages
    .filter((s) => s.stage === 'resolve')
    .map((s) => parseInstant(s.started_at))
    .filter((t): t is number => t != null)
  if (!resolveStarts.length) return ''
  const from = Math.min(...resolveStarts)
  const assembleEnds = stages
    .filter((s) => s.stage === 'assemble')
    .map((s) => parseInstant(s.finished_at))
    .filter((t): t is number => t != null)
  const to = assembleEnds.length ? Math.max(...assembleEnds) : now
  if (to < from) return ''
  return formatElapsedMs(to - from)
}

/** Catalog voice label with an explicit gender tag, e.g. `Heart (female)`. */
export function stockVoiceLabel(name: string, gender: string | null | undefined): string {
  return gender ? `${name} (${gender})` : name
}
