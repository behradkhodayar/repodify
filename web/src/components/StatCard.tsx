import type { LucideIcon } from 'lucide-react'
import { motion } from 'framer-motion'
import { AnimatedNumber } from './AnimatedNumber'
import { Card } from './ui/card'
import { cn } from '../lib/utils'

export function StatCard({
  label,
  value,
  icon: Icon,
  suffix,
  index = 0,
  highlight = false,
}: {
  label: string
  value: number
  icon: LucideIcon
  suffix?: string
  index?: number
  highlight?: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06, ease: [0.22, 1, 0.36, 1] }}
    >
      <Card className="relative overflow-hidden p-5 transition-shadow hover:shadow-lift">
        <div
          className={cn(
            'pointer-events-none absolute -right-6 -top-8 size-24 rounded-full blur-2xl',
            highlight ? 'bg-primary/20' : 'bg-primary/5',
          )}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
          <span
            className={cn(
              'flex size-8 items-center justify-center rounded-md',
              highlight ? 'bg-wave text-primary-foreground' : 'bg-primary/10 text-primary',
            )}
          >
            <Icon className="size-[18px]" />
          </span>
        </div>
        <div className="mt-3 flex items-baseline gap-1.5">
          <AnimatedNumber
            value={value}
            className="tabular font-display text-3xl font-semibold tracking-tight"
          />
          {suffix && <span className="text-sm font-medium text-muted-foreground">{suffix}</span>}
        </div>
      </Card>
    </motion.div>
  )
}
