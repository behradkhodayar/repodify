import { Menu } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Button } from '../ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '../ui/sheet'
import { ApiStatus } from './ApiStatus'
import { Logo } from './Logo'
import { NavLinks } from './NavLinks'
import { ThemeToggle } from './ThemeToggle'

function titleFor(pathname: string): string {
  if (pathname === '/') return 'Overview'
  if (pathname.startsWith('/new')) return 'New digest'
  if (/^\/jobs\/.+/.test(pathname)) return 'Job detail'
  if (pathname.startsWith('/jobs')) return 'History'
  if (pathname.startsWith('/settings')) return 'Settings'
  return 'repodify'
}

export function Topbar() {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur-md sm:px-6">
      <div className="lg:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              <Menu className="size-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left">
            <SheetTitle>Navigation</SheetTitle>
            <div className="flex h-16 items-center px-5">
              <Logo animate={false} />
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2">
              <NavLinks indicatorId="nav-active-mobile" onNavigate={() => setOpen(false)} />
            </div>
            <div className="p-3">
              <ApiStatus />
            </div>
          </SheetContent>
        </Sheet>
      </div>

      <Link to="/" className="lg:hidden" aria-label="repodify home">
        <Logo animate={false} />
      </Link>

      <h1 className="hidden font-display text-base font-semibold tracking-tight lg:block">
        {titleFor(pathname)}
      </h1>

      <div className="ml-auto flex items-center gap-1.5">
        <Button asChild variant="wave" size="sm" className="hidden sm:inline-flex">
          <Link to="/new">New digest</Link>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  )
}
