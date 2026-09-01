import { statusLabel } from '../lib/format'
import { cn } from '../lib/utils'

const DOT: Record<string, string> = {
  completed: 'bg-status-done',
  running: 'bg-status-running',
  awaiting_review: 'bg-status-running',
  awaiting_config: 'bg-status-running',
  queued: 'bg-status-idle',
  failed: 'bg-status-failed',
}

/** Job status as a neutral pill with a fully-opaque colored dot. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const pulsing = status === 'running' || status === 'awaiting_review' || status === 'awaiting_config'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2.5 py-0.5 text-xs font-medium text-foreground',
        className,
      )}
    >
      <span
        className={cn('size-1.5 rounded-full', DOT[status] ?? 'bg-status-idle', pulsing && 'animate-pulse')}
      />
      {statusLabel(status)}
    </span>
  )
}
