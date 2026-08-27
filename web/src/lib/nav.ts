import { History, LayoutDashboard, Settings, Sparkles, type LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Match the path exactly (used for the index route). */
  end?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/new', label: 'New digest', icon: Sparkles },
  { to: '/jobs', label: 'History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]
