import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateJob, useResolveFeed } from '../api/queries'
import { EpisodePicker } from '../components/EpisodePicker'

export function NewDigest() {
  const [url, setUrl] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [targetMinutes, setTargetMinutes] = useState(30)
  const [hostCount, setHostCount] = useState(1)
  const [reviewVoices, setReviewVoices] = useState(false)
  const resolve = useResolveFeed()
  const create = useCreateJob()
  const navigate = useNavigate()

  function toggle(guid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(guid)) next.delete(guid)
      else next.add(guid)
      return next
    })
  }

  async function onCreate() {
    const { job_id } = await create.mutateAsync({
      feed_url: url,
      episode_ids: [...selected],
      host_count: hostCount,
      target_minutes: targetMinutes,
      review_voices: reviewVoices,
    })
    navigate(`/jobs/${job_id}`)
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">New digest</h1>
      <div className="flex gap-2">
        <input
          className="border rounded px-2 py-1 flex-1"
          aria-label="Feed URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/feed.xml"
        />
        <button className="bg-slate-900 text-white rounded px-3" onClick={() => resolve.mutate(url)}>
          Resolve
        </button>
      </div>
      {resolve.isError && <p className="text-red-600">Couldn't fetch that feed.</p>}
      {resolve.data && (
        <>
          <EpisodePicker episodes={resolve.data.episodes} selected={selected} onToggle={toggle} />
          <div className="flex gap-4 items-center">
            <label>
              Minutes{' '}
              <input
                type="number"
                className="border rounded w-20 px-1"
                value={targetMinutes}
                onChange={(e) => setTargetMinutes(Number(e.target.value))}
              />
            </label>
            <label>
              Hosts{' '}
              <select
                className="border rounded ml-1"
                value={hostCount}
                onChange={(e) => setHostCount(Number(e.target.value))}
              >
                <option value={1}>1 (narrator)</option>
                <option value={2}>2 (dialogue)</option>
              </select>
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={reviewVoices}
                onChange={(e) => setReviewVoices(e.target.checked)}
              />
              Assign voices per speaker
            </label>
            <button
              className="bg-emerald-600 text-white rounded px-3 py-1 disabled:opacity-50"
              disabled={selected.size === 0 || create.isPending}
              onClick={onCreate}
            >
              Create digest
            </button>
          </div>
        </>
      )}
      {create.data && <p>Created job {create.data.job_id}…</p>}
    </div>
  )
}
