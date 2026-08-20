import { useRef } from 'react'
import type { ChapterOut } from '../api/types'

export function AudioPlayer({ jobId, chapters }: { jobId: string; chapters: ChapterOut[] }) {
  const ref = useRef<HTMLAudioElement>(null)
  function seek(start: number) {
    if (ref.current) ref.current.currentTime = start
  }
  return (
    <div className="space-y-2">
      <audio ref={ref} controls src={`/jobs/${jobId}/audio?format=mp3`} className="w-full" />
      <ul className="text-sm">
        {chapters.map((c, i) => (
          <li key={i}>
            <button className="underline" onClick={() => seek(c.start_s)}>
              {c.title}
            </button>
          </li>
        ))}
      </ul>
      <div className="text-sm">
        Download:{' '}
        <a className="underline" href={`/jobs/${jobId}/audio?format=mp3`}>
          mp3
        </a>
        {' · '}
        <a className="underline" href={`/jobs/${jobId}/audio?format=wav`}>
          wav
        </a>
      </div>
    </div>
  )
}
