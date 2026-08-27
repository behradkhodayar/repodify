import { Plus, Radio } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useJobs } from '../api/queries'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { Button } from '../components/ui/button'
import { Card, CardContent } from '../components/ui/card'
import { Skeleton } from '../components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { relativeTime, shortId } from '../lib/format'

export function Jobs() {
  const { data, isLoading } = useJobs()
  const navigate = useNavigate()

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="History" description="Every digest you've created." />
        <Card>
          <CardContent className="space-y-2 pt-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!data || data.total === 0) {
    return (
      <div className="space-y-6">
        <PageHeader title="History" description="Every digest you've created." />
        <EmptyState
          icon={Radio}
          title="No digests yet"
          description="Create one from New digest and it'll show up here with live status."
          action={
            <Button asChild variant="wave">
              <Link to="/new">
                <Plus className="size-4" /> New digest
              </Link>
            </Button>
          }
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="History" description={`${data.total} digest${data.total === 1 ? '' : 's'} created.`} />
      <Card>
        <CardContent className="pt-6">
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
              {data.jobs.map((j) => (
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
        </CardContent>
      </Card>
    </div>
  )
}
