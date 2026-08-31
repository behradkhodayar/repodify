import { motion } from 'framer-motion'
import { Check, Loader2, Minus, X } from 'lucide-react'
import type { StageOut } from '../api/types'
import { elapsedLabel, parsePercent, PIPELINE_STAGES } from '../lib/format'
import { useNow } from '../lib/useNow'
import { cn } from '../lib/utils'
import { Progress } from './ui/progress'

function node(state: string) {
  switch (state) {
    case 'done':
      return { ring: 'bg-primary text-primary-foreground', icon: <Check className="size-4" /> }
    case 'running':
      return {
        ring: 'bg-status-running/15 text-status-running animate-pulse-ring',
        icon: <Loader2 className="size-4 animate-spin" />,
      }
    case 'failed':
      return { ring: 'bg-status-failed text-white', icon: <X className="size-4" /> }
    case 'skipped':
      return { ring: 'bg-muted text-muted-foreground', icon: <Minus className="size-4" /> }
    default:
      return {
        ring: 'border border-border bg-card text-muted-foreground',
        icon: <span className="size-1.5 rounded-full bg-current" />,
      }
  }
}

function mergeStages(stages: StageOut[]): StageOut[] {
  const byName = new Map(stages.map((s) => [s.stage, s]))
  return PIPELINE_STAGES.map(
    (name) =>
      byName.get(name) ?? {
        stage: name,
        state: 'pending',
        detail: null,
        started_at: null,
        finished_at: null,
      },
  )
}

export function StageProgress({ stages }: { stages: StageOut[] }) {
  const rows = mergeStages(stages)
  const ticking = rows.some((s) => s.state === 'running' && s.started_at)
  const now = useNow(ticking)

  return (
    <ol className="relative">
      {rows.map((s, i) => {
        const isLast = i === rows.length - 1
        const { ring, icon } = node(s.state)
        const pct = s.state === 'running' ? parsePercent(s.detail) : null
        const time =
          s.state === 'running'
            ? elapsedLabel(s.started_at, null, now)
            : s.state === 'done' || s.state === 'failed'
              ? elapsedLabel(s.started_at, s.finished_at)
              : ''
        return (
          <motion.li
            key={s.stage}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: i * 0.05 }}
            className="relative flex gap-4 pb-6 last:pb-0"
          >
            {!isLast && (
              <span
                className={cn(
                  'absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-px',
                  s.state === 'done' ? 'bg-primary/40' : 'bg-border',
                )}
              />
            )}
            <span
              className={cn(
                'relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full',
                ring,
              )}
            >
              {icon}
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium capitalize">{s.stage.replace(/_/g, ' ')}</span>
                {time && (
                  <span className="tabular shrink-0 font-mono text-[11px] text-muted-foreground">
                    {time}
                  </span>
                )}
              </div>
              {s.detail && <p className="mt-0.5 text-sm text-muted-foreground">{s.detail}</p>}
              {pct !== null && <Progress value={pct} className="mt-2 h-1.5" />}
            </div>
          </motion.li>
        )
      })}
    </ol>
  )
}
