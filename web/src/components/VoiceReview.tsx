import { useState } from 'react'
import { useSpeakers, useSubmitVoices, useVoices } from '../api/queries'
import type { VoiceAssignment } from '../api/types'

const CLONE = 'clone'

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

  if (speakers.isLoading) return <p>Loading speakers…</p>

  return (
    <div className="space-y-3 border rounded p-4">
      <h2 className="font-semibold">Assign a voice to each speaker</h2>
      <p className="text-sm text-slate-600">
        Diarization detected {list.length} speaker{list.length === 1 ? '' : 's'}. Clone each
        one&apos;s real voice, or pick a stock voice. Only clone voices you have consent to use.
      </p>
      <ul className="space-y-2">
        {list.map((s) => (
          <li key={s.speaker_id} className="flex items-center gap-3">
            <span className="font-mono text-sm w-32">{s.display_name ?? s.speaker_id}</span>
            <span className="text-xs text-slate-500 w-16">{Math.round(s.speaking_seconds)}s</span>
            <select
              aria-label={`Voice for ${s.speaker_id}`}
              className="border rounded px-2 py-1"
              value={choiceFor(s.speaker_id)}
              onChange={(e) => setChoices((p) => ({ ...p, [s.speaker_id]: e.target.value }))}
            >
              <option value={CLONE}>Clone this speaker</option>
              {(voices.data?.stock_voices ?? []).map((v) => (
                <option key={v} value={v}>
                  Stock: {v}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
      <button
        className="bg-emerald-600 text-white rounded px-3 py-1 disabled:opacity-50"
        disabled={list.length === 0 || submit.isPending}
        onClick={onSubmit}
      >
        Generate digest
      </button>
      {submit.isError && <p className="text-red-600 text-sm">Couldn&apos;t submit voices.</p>}
    </div>
  )
}
