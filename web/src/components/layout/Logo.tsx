import { cn } from '../../lib/utils'
import { BrandMark } from '../BrandMark'

/** repodify wordmark: gold waveform chip + Space Grotesk logotype. */
export function Logo({ className }: { className?: string; animate?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <BrandMark className="size-8 shadow-glow" />
      <span className="font-display text-lg font-semibold tracking-tight">
        <span className="text-wave">re</span>
        <span className="text-foreground">pod</span>
        <span className="text-wave">ify</span>
      </span>
    </span>
  )
}
