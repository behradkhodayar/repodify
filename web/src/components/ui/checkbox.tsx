import * as React from 'react'
import { cn } from '../../lib/utils'

/**
 * Native checkbox, restyled via `accent-color`. Stays a real checkbox input so
 * `getByRole('checkbox')` and click-to-toggle keep working.
 */
export const Checkbox = React.forwardRef<
  HTMLInputElement,
  Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    type="checkbox"
    className={cn(
      'size-4 shrink-0 cursor-pointer rounded border-input accent-[hsl(var(--primary))]',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-1 focus-visible:ring-offset-background',
      className,
    )}
    {...props}
  />
))
Checkbox.displayName = 'Checkbox'
