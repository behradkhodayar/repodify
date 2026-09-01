import { cn } from '../lib/utils'

/**
 * The repodify signature mark: a row of gold equalizer bars.
 * Animated by default; the global reduced-motion rule freezes it when asked.
 */
export function Waveform({
  bars = 5,
  animate = true,
  className,
  barClassName = 'bg-wave',
}: {
  bars?: number
  animate?: boolean
  className?: string
  barClassName?: string
}) {
  return (
    <div className={cn('flex h-4 items-center gap-[3px]', className)} aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <span
          key={i}
          className={cn('h-full w-[3px] origin-center rounded-full', barClassName)}
          style={
            animate
              ? { animation: `wave-bar ${0.9 + ((i * 7) % 5) * 0.16}s ease-in-out ${i * 0.11}s infinite` }
              : { transform: `scaleY(${0.4 + ((i * 5) % 3) * 0.28})` }
          }
        />
      ))}
    </div>
  )
}
