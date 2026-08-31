import { Link } from 'react-router-dom'
import { ApiStatus } from './ApiStatus'
import { Logo } from './Logo'
import { NavLinks } from './NavLinks'

/** Persistent left sidebar (desktop, >= lg). */
export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/40 lg:flex">
      <div className="flex h-16 items-center px-5">
        <Link to="/" aria-label="repodify home">
          <Logo />
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <p className="px-3 pb-2 text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground/70">
          Workspace
        </p>
        <NavLinks />
      </div>
      <div className="p-3">
        <ApiStatus />
      </div>
    </aside>
  )
}
