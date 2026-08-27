import { Download, Headphones, Play } from 'lucide-react'
import { useRef } from 'react'
import type { ChapterOut } from '../api/types'
import { Button } from './ui/button'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'

function formatTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

export function AudioPlayer({ jobId, chapters }: { jobId: string; chapters: ChapterOut[] }) {
  const ref = useRef<HTMLAudioElement>(null)
  function seek(start: number) {
    if (ref.current) ref.current.currentTime = start
  }
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <Headphones className="size-[18px] text-primary" /> Your digest
        </CardTitle>
        <div className="flex items-center gap-1.5">
          <Button asChild variant="outline" size="sm">
            <a href={`/jobs/${jobId}/audio?format=mp3`}>
              <Download /> MP3
            </a>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={`/jobs/${jobId}/audio?format=wav`}>
              <Download /> WAV
            </a>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <audio ref={ref} controls src={`/jobs/${jobId}/audio?format=mp3`} className="w-full" />
        {chapters.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Chapters
            </p>
            <ul className="space-y-0.5">
              {chapters.map((c, i) => (
                <li key={i}>
                  <button
                    onClick={() => seek(c.start_s)}
                    className="group flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted"
                  >
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                      <Play className="size-3" />
                    </span>
                    <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {formatTime(c.start_s)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
