import { cn } from '../lib/utils'

const MARK_SRC = `${import.meta.env.BASE_URL}favicon.svg`

/** Official gold waveform chip from `web/public/favicon.svg`. */
export function BrandMark({
  className,
  alt = '',
}: {
  className?: string
  alt?: string
}) {
  return (
    <img
      src={MARK_SRC}
      alt={alt}
      draggable={false}
      aria-hidden={alt === '' ? true : undefined}
      className={cn('shrink-0 rounded-[25%]', className)}
    />
  )
}
