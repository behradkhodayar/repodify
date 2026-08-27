import { KeyRound } from 'lucide-react'
import { Link } from 'react-router-dom'

export function TokenBanner() {
  return (
    <div className="flex items-center gap-2.5 border-b border-status-running/20 bg-status-running/10 px-4 py-2.5 text-sm text-foreground">
      <KeyRound className="size-4 shrink-0 text-status-running" />
      <span>
        This API needs a token.{' '}
        <Link to="/settings" className="font-medium text-primary underline-offset-2 hover:underline">
          Set it in Settings
        </Link>
        .
      </span>
    </div>
  )
}
