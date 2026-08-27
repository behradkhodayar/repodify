import { motion } from 'framer-motion'
import { Check, Loader2, Minus, X } from 'lucide-react'
import type { StageOut } from '../api/types'
import { cn } from '../lib/utils'

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

export function StageProgress({ stages }: { stages: StageOut[] }) {
  return (
    <ol className="relative">
      {stages.map((s, i) => {
        const isLast = i === stages.length - 1
        const { ring, icon } = node(s.state)
        return (
          <motion.li
            key={i}
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
              <span className="text-sm font-medium capitalize">{s.stage.replace(/_/g, ' ')}</span>
              {s.detail && <p className="mt-0.5 text-sm text-muted-foreground">{s.detail}</p>}
            </div>
          </motion.li>
        )
      })}
    </ol>
  )
}
