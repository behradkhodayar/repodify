import { Link } from 'react-router-dom'
import { useToken } from '../../lib/useToken'
import { cn } from '../../lib/utils'

/** Sidebar footer chip: shows whether an API token is configured. */
export function ApiStatus() {
  const { token } = useToken()
  const configured = token.length > 0
  return (
    <Link
      to="/settings"
      className="flex items-center gap-2.5 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted"
    >
      <span className="relative flex size-2">
        <span
          className={cn(
            'absolute inline-flex size-full rounded-full opacity-70',
            configured ? 'animate-ping bg-status-done' : '',
          )}
        />
        <span
          className={cn(
            'relative inline-flex size-2 rounded-full',
            configured ? 'bg-status-done' : 'bg-status-idle',
          )}
        />
      </span>
      <span className="font-medium text-foreground">
        {configured ? 'API token set' : 'No API token'}
      </span>
    </Link>
  )
}
