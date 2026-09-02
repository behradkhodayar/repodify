import { motion } from 'framer-motion'
import { Activity, CheckCircle2, Clock, Plus, Radio, Sparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useJobs } from '../api/queries'
import { BrandMark } from '../components/BrandMark'
import { EmptyState } from '../components/EmptyState'
import { StatCard } from '../components/StatCard'
import { StatusBadge } from '../components/StatusBadge'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Skeleton } from '../components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { isActive, relativeTime, shortId } from '../lib/format'

export function Overview() {
  const { data, isLoading } = useJobs()
  const navigate = useNavigate()
  const jobs = data?.jobs ?? []
  const total = data?.total ?? 0
  const completed = jobs.filter((j) => j.status === 'completed').length
  const inProgress = jobs.filter((j) => isActive(j.status)).length
  const minutes = jobs.reduce((sum, j) => sum + (j.target_minutes ?? 0), 0)
  const recent = [...jobs]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 8)

  return (
    <div className="space-y-6">
      {/* Hero — the thesis: long feeds cut into tight listens. */}
      <Card className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/[0.08] via-transparent to-transparent" />
        <div className="relative flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div className="max-w-md space-y-3">
            <Badge variant="default" className="gap-1.5">
              <Sparkles className="size-3.5" /> AI audio digests
            </Badge>
            <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
              Turn long feeds into tight listens.
            </h2>
            <p className="text-sm text-muted-foreground">
              Point repodify at a podcast feed, pick the episodes, and get a short digest voiced by
              the real cast.
            </p>
            <Button asChild variant="wave">
              <Link to="/new">
                <Plus className="size-4" /> New digest
              </Link>
            </Button>
          </div>
          <BrandMark className="size-24 shadow-glow sm:size-28" />
        </div>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <StatCard label="Total digests" value={total} icon={Radio} index={0} />
            <StatCard label="Completed" value={completed} icon={CheckCircle2} index={1} />
            <StatCard
              label="In progress"
              value={inProgress}
              icon={Activity}
              index={2}
              highlight={inProgress > 0}
            />
            <StatCard label="Digest minutes" value={minutes} icon={Clock} suffix="min" index={3} />
          </>
        )}
      </div>

      {/* Recent digests */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.24, ease: [0.22, 1, 0.36, 1] }}
      >
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent digests</CardTitle>
            {total > 0 && (
              <Button asChild variant="ghost" size="sm">
                <Link to="/jobs">View all</Link>
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <EmptyState
                icon={Radio}
                title="No digests yet"
                description="Turn your first feed into a tight listen — it only takes a URL."
                action={
                  <Button asChild variant="wave">
                    <Link to="/new">
                      <Plus className="size-4" /> New digest
                    </Link>
                  </Button>
                }
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Digest</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Length</TableHead>
                    <TableHead className="text-right">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((j) => (
                    <TableRow
                      key={j.id}
                      data-clickable="true"
                      onClick={() => navigate(`/jobs/${j.id}`)}
                    >
                      <TableCell>
                        <Link
                          to={`/jobs/${j.id}`}
                          className="font-mono text-sm text-foreground hover:text-primary"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {shortId(j.id)}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={j.status} />
                      </TableCell>
                      <TableCell className="tabular text-muted-foreground">
                        {j.target_minutes} min
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {relativeTime(j.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
