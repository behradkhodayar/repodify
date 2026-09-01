import { cn } from '../../lib/utils'
import { Waveform } from '../Waveform'

/** repodify wordmark: animated waveform glyph + Space Grotesk logotype. */
export function Logo({ className, animate = true }: { className?: string; animate?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <span className="flex size-8 items-center justify-center rounded-md bg-wave shadow-glow">
        <Waveform bars={4} animate={animate} className="h-3.5" barClassName="bg-primary-foreground/90" />
      </span>
      <span className="font-display text-lg font-semibold tracking-tight">
        <span className="text-wave">re</span>
        <span className="text-foreground">pod</span>
        <span className="text-wave">ify</span>
      </span>
    </span>
  )
}
