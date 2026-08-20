import { Link } from 'react-router-dom'

export function TokenBanner() {
  return (
    <div className="bg-amber-100 text-amber-900 px-4 py-2 text-sm">
      This API needs a token.{' '}
      <Link to="/settings" className="underline font-medium">
        Set it in Settings
      </Link>
      .
    </div>
  )
}
