import { useParams } from 'react-router-dom'
import { useJob, useResult } from '../api/queries'
import { AudioPlayer } from '../components/AudioPlayer'
import { StageProgress } from '../components/StageProgress'
import { VoiceReview } from '../components/VoiceReview'

export function JobDetail() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const completed = job.data?.status === 'completed'
  const result = useResult(id, completed)

  if (job.isLoading) return <p>Loading…</p>
  if (!job.data) return <p>Job not found.</p>

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Job {id}</h1>
      <p className="text-sm text-slate-600">Status: {job.data.status}</p>
      <StageProgress stages={job.data.stages} />
      {job.data.status === 'awaiting_review' && <VoiceReview jobId={id} />}
      {job.data.status === 'failed' && (
        <div className="text-red-600 text-sm">
          <p>This job failed.</p>
          <ul className="list-disc ml-5">
            {(job.data.report.skipped ?? []).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      {completed && result.data && (
        <div className="space-y-3">
          <p>{result.data.summary}</p>
          <AudioPlayer jobId={id} chapters={result.data.chapters} />
        </div>
      )}
    </div>
  )
}
