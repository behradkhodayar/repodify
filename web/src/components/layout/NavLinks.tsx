import { motion } from 'framer-motion'
import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from '../../lib/nav'
import { cn } from '../../lib/utils'
import { Waveform } from '../Waveform'

/** Shared nav list for the sidebar and the mobile drawer. */
export function NavLinks({
  onNavigate,
  indicatorId = 'nav-active',
}: {
  onNavigate?: () => void
  indicatorId?: string
}) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'text-primary'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <motion.span
                  layoutId={indicatorId}
                  className="absolute inset-0 rounded-md bg-primary/10 ring-1 ring-primary/20"
                  transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                />
              )}
              <item.icon className="relative z-10 size-[18px] shrink-0" />
              <span className="relative z-10">{item.label}</span>
              {isActive && (
                <span className="relative z-10 ml-auto">
                  <Waveform bars={3} className="h-3" />
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
