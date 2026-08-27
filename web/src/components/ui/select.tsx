import * as React from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '../../lib/utils'

/**
 * Native `<select>`, restyled with a custom chevron. Stays a real select so
 * `getByLabelText` + `fireEvent.change(..., { target: { value } })` keep working.
 */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <div className="relative inline-flex w-full">
    <select
      ref={ref}
      className={cn(
        'h-9 w-full appearance-none rounded-md border border-input bg-background pl-3 pr-9 text-sm shadow-sm transition-colors',
        'focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      {children}
    </select>
    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
  </div>
))
Select.displayName = 'Select'
