import { Link } from 'react-router-dom'
import { useJobs } from '../api/queries'

export function Jobs() {
  const { data, isLoading } = useJobs()
  if (isLoading) return <p>Loading…</p>
  if (!data || data.total === 0) return <p>No digests yet. Create one from “New digest”.</p>
  return (
    <ul className="divide-y border rounded">
      {data.jobs.map((j) => (
        <li key={j.id} className="p-2 flex justify-between">
          <Link to={`/jobs/${j.id}`} className="underline">
            {j.id}
          </Link>
          <span className="text-sm text-slate-600">
            {j.status} · {j.target_minutes} min
          </span>
        </li>
      ))}
    </ul>
  )
}
