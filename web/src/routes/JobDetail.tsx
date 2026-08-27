import { AlertTriangle, ArrowLeft, FileText } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useJob, useResult } from '../api/queries'
import { AudioPlayer } from '../components/AudioPlayer'
import { StageProgress } from '../components/StageProgress'
import { StatusBadge } from '../components/StatusBadge'
import { Waveform } from '../components/Waveform'
import { VoiceReview } from '../components/VoiceReview'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Progress } from '../components/ui/progress'
import { Skeleton } from '../components/ui/skeleton'
import { shortId } from '../lib/format'

export function JobDetail() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const completed = job.data?.status === 'completed'
  const result = useResult(id, completed)

  if (job.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-48" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-1" />
          <Skeleton className="h-64 lg:col-span-2" />
        </div>
      </div>
    )
  }

  if (!job.data) {
    return (
      <Card>
        <CardContent className="py-16 text-center text-muted-foreground">
          Job not found.
        </CardContent>
      </Card>
    )
  }

  const { status, stages } = job.data
  const doneCount = stages.filter((s) => s.state === 'done').length
  const pct = stages.length ? Math.round((doneCount / stages.length) * 100) : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            to="/jobs"
            className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> History
          </Link>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            Digest <span className="font-mono text-xl">{shortId(id)}</span>
          </h1>
        </div>
        <StatusBadge status={status} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Pipeline</CardTitle>
            <div className="space-y-1.5 pt-1">
              <Progress value={pct} />
              <p className="text-xs text-muted-foreground">
                {doneCount}/{stages.length} stages · {pct}%
              </p>
            </div>
          </CardHeader>
          <CardContent>
            <StageProgress stages={stages} />
          </CardContent>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          {status === 'awaiting_review' && <VoiceReview jobId={id} />}

          {status === 'failed' && (
            <Card className="border-status-failed/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-status-failed">
                  <AlertTriangle className="size-[18px] text-status-failed" /> This job failed
                </CardTitle>
              </CardHeader>
              <CardContent>
                {(job.data.report.skipped ?? []).length > 0 ? (
                  <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                    {(job.data.report.skipped ?? []).map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Something went wrong during processing. Try creating the digest again.
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {(status === 'queued' || status === 'running') && (
            <Card>
              <CardContent className="flex items-center gap-4 py-8">
                <Waveform bars={12} className="h-10" />
                <div>
                  <p className="font-display font-medium">Working on your digest…</p>
                  <p className="text-sm text-muted-foreground">
                    This page updates live as each stage completes.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {completed && result.data && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="size-[18px] text-primary" /> Summary
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {result.data.summary}
                  </p>
                </CardContent>
              </Card>
              <AudioPlayer jobId={id} chapters={result.data.chapters} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
