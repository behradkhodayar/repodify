import { Loader2, Mic, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useSpeakers, useSubmitVoices, useVoices } from '../api/queries'
import type { VoiceAssignment } from '../api/types'
import { stockVoiceLabel } from '../lib/format'
import { PlaySample } from './PlaySample'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Select } from './ui/select'
import { Skeleton } from './ui/skeleton'

const CLONE = 'clone'

function initials(name: string): string {
  const cleaned = name.replace(/[^a-zA-Z0-9]/g, '')
  return (cleaned.slice(-2) || '??').toUpperCase()
}

/**
 * Shown while a job is `awaiting_review`: the detected speakers, each with a
 * dropdown to clone their real voice or pick a stock voice. Submitting resumes
 * the job into a speaker-preserving digest.
 */
export function VoiceReview({ jobId }: { jobId: string }) {
  const speakers = useSpeakers(jobId, true)
  const voices = useVoices()
  const submit = useSubmitVoices(jobId)
  const [choices, setChoices] = useState<Record<string, string>>({})

  const list = speakers.data?.speakers ?? []
  const choiceFor = (id: string) => choices[id] ?? CLONE

  async function onSubmit() {
    const voice_assignments: VoiceAssignment[] = list.map((s) => {
      const choice = choiceFor(s.speaker_id)
      return choice === CLONE
        ? { speaker_id: s.speaker_id, mode: 'clone' }
        : { speaker_id: s.speaker_id, mode: 'stock', stock_voice: choice }
    })
    await submit.mutateAsync({ voice_assignments })
  }

  if (speakers.isLoading) {
    return (
      <Card>
        <CardContent className="space-y-2 py-6">
          <Skeleton className="h-5 w-64" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Assign a voice to each speaker
        </CardTitle>
        <CardDescription>
          Diarization detected {list.length} speaker{list.length === 1 ? '' : 's'}. Clone each
          one&apos;s real voice, or pick a stock voice.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          <ShieldCheck className="size-4 shrink-0 text-primary" />
          <span>Only clone voices you have consent to use.</span>
        </div>

        <ul className="space-y-2">
          {list.map((s) => {
            const choice = choiceFor(s.speaker_id)
            const selected = (voices.data?.voices ?? []).find((v) => v.id === choice)
            return (
              <li
                key={s.speaker_id}
                className="flex flex-col gap-3 rounded-md border border-border p-3 sm:flex-row sm:items-center"
              >
                <span className="flex items-center gap-2.5 sm:w-52">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-medium text-primary">
                    {initials(s.display_name ?? s.speaker_id)}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-sm">
                      {s.display_name ?? s.speaker_id}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {Math.round(s.speaking_seconds)}s speaking
                    </span>
                  </span>
                </span>
                <span className="flex min-w-0 flex-1 items-center gap-1 sm:ml-auto sm:max-w-xs">
                  {choice !== CLONE ? (
                    <PlaySample voiceId={choice} name={selected?.name ?? choice} />
                  ) : null}
                  <Select
                    aria-label={`Voice for ${s.speaker_id}`}
                    value={choice}
                    onChange={(e) => setChoices((p) => ({ ...p, [s.speaker_id]: e.target.value }))}
                  >
                    <option value={CLONE}>Clone this speaker</option>
                    {(voices.data?.voices ?? []).map((v) => (
                      <option key={v.id} value={v.id}>
                        Stock: {stockVoiceLabel(v.name, v.gender)}
                      </option>
                    ))}
                  </Select>
                </span>
              </li>
            )
          })}
        </ul>

        <div className="flex items-center justify-end gap-3">
          {submit.isError && (
            <p className="text-sm text-status-failed">Couldn&apos;t submit voices. Try again.</p>
          )}
          <Button
            variant="wave"
            disabled={list.length === 0 || submit.isPending}
            onClick={onSubmit}
          >
            {submit.isPending ? (
              <>
                <Loader2 className="animate-spin" /> Generating
              </>
            ) : (
              <>
                <Sparkles /> Generate digest
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
