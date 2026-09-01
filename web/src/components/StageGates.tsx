import { Cpu, Loader2, Mic, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useContinueJob, useLlmSettings, useVoices } from '../api/queries'
import type { GateInfo, JobStatusResponse, SpeakerOut } from '../api/types'
import { stockVoiceLabel } from '../lib/format'
import { PlaySample } from './PlaySample'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Checkbox } from './ui/checkbox'
import { Input } from './ui/input'
import { Select } from './ui/select'

const WHISPER_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v3'] as const

function ModeToggle({
  value,
  onChange,
  localLabel,
  byokLabel,
}: {
  value: 'local' | 'byok'
  onChange: (v: 'local' | 'byok') => void
  localLabel: string
  byokLabel: string
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Button type="button" variant={value === 'local' ? 'default' : 'outline'} onClick={() => onChange('local')}>
        {localLabel}
      </Button>
      <Button type="button" variant={value === 'byok' ? 'default' : 'outline'} onClick={() => onChange('byok')}>
        {byokLabel}
      </Button>
    </div>
  )
}

function WaitHint() {
  return (
    <p className="text-xs text-muted-foreground">
      You can close this page or stop the app; this job waits here.
    </p>
  )
}

function MissingKey({ missing, configured }: { missing: boolean; configured: boolean }) {
  if (!missing || configured) return null
  return (
    <p className="text-xs text-status-failed">
      Set the API key in Settings / .env before using a hosted backend.
    </p>
  )
}

export function StageGates({ job }: { job: JobStatusResponse }) {
  const gate = job.gate ?? job.report.gate
  if (job.status !== 'awaiting_config' && job.status !== 'awaiting_review') return null
  if (gate === 'transcribe') return <TranscribeGate jobId={job.id} info={job.gate_info} />
  if (gate === 'diarize') return <DiarizeGate jobId={job.id} info={job.gate_info} />
  if (gate === 'voices' || job.status === 'awaiting_review') {
    return <VoicesGate jobId={job.id} speakers={job.gate_info?.speakers ?? []} />
  }
  if (gate === 'summarize') return <SummarizeGate jobId={job.id} info={job.gate_info} />
  if (gate === 'tts') return <TtsGate jobId={job.id} info={job.gate_info} />
  return null
}

function TranscribeGate({ jobId, info }: { jobId: string; info?: GateInfo }) {
  const cont = useContinueJob(jobId)
  const [mode, setMode] = useState<'local' | 'byok'>('local')
  const [localModel, setLocalModel] = useState(info?.whisper_model ?? 'small')
  const [byokModel, setByokModel] = useState('openai/whisper-large-v3')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Transcribe
        </CardTitle>
        <CardDescription>Run speech-to-text locally or with your OpenRouter key.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ModeToggle value={mode} onChange={setMode} localLabel="Local · faster-whisper" byokLabel="BYOK · OpenRouter" />
        {mode === 'local' ? (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Whisper model</span>
            <Select aria-label="Whisper model" value={localModel} onChange={(e) => setLocalModel(e.target.value)}>
              {WHISPER_SIZES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </label>
        ) : (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">OpenRouter STT model</span>
            <Input aria-label="STT model" value={byokModel} onChange={(e) => setByokModel(e.target.value)} />
            <MissingKey missing={mode === 'byok'} configured={!!info?.openrouter_configured} />
          </label>
        )}
        <WaitHint />
        <div className="flex justify-end">
          <Button
            variant="wave"
            disabled={cont.isPending || (mode === 'byok' && !info?.openrouter_configured)}
            onClick={() =>
              cont.mutate({
                gate: 'transcribe',
                payload: { mode, model: mode === 'local' ? localModel : byokModel },
              })
            }
          >
            {cont.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Continue
          </Button>
        </div>
        {cont.isError && <p className="text-sm text-status-failed">Couldn&apos;t continue. Try again.</p>}
      </CardContent>
    </Card>
  )
}

function DiarizeGate({ jobId, info }: { jobId: string; info?: GateInfo }) {
  const cont = useContinueJob(jobId)
  const [assign, setAssign] = useState(false)
  const [mode, setMode] = useState<'local' | 'byok'>('local')
  const [byokModel, setByokModel] = useState('community-1')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Diarize
        </CardTitle>
        <CardDescription>Optionally detect who spoke, then assign voices after this step.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2">
          <Checkbox checked={assign} onChange={(e) => setAssign(e.target.checked)} />
          <span className="text-sm font-medium">Assign voices per speaker</span>
        </label>
        {assign && (
          <>
            <ModeToggle
              value={mode}
              onChange={setMode}
              localLabel="Local · pyannote"
              byokLabel="BYOK · pyannoteAI"
            />
            {mode === 'byok' && (
              <label className="block space-y-1.5">
                <span className="text-sm font-medium">pyannoteAI model</span>
                <Input aria-label="Diarize model" value={byokModel} onChange={(e) => setByokModel(e.target.value)} />
                <MissingKey missing configured={!!info?.pyannoteai_configured} />
              </label>
            )}
            {mode === 'local' && !info?.hf_token_configured && (
              <p className="text-xs text-muted-foreground">Local pyannote needs HF_TOKEN in .env.</p>
            )}
          </>
        )}
        <WaitHint />
        <div className="flex justify-end">
          <Button
            variant="wave"
            disabled={
              cont.isPending || (assign && mode === 'byok' && !info?.pyannoteai_configured)
            }
            onClick={() =>
              cont.mutate({
                gate: 'diarize',
                payload: assign
                  ? { assign_voices: true, mode, model: mode === 'byok' ? byokModel : undefined }
                  : { assign_voices: false },
              })
            }
          >
            {cont.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Continue
          </Button>
        </div>
        {cont.isError && <p className="text-sm text-status-failed">Couldn&apos;t continue. Try again.</p>}
      </CardContent>
    </Card>
  )
}

function VoicesGate({ jobId, speakers }: { jobId: string; speakers: SpeakerOut[] }) {
  const voices = useVoices()
  const cont = useContinueJob(jobId)
  const [useOriginal, setUseOriginal] = useState(true)
  const [stock, setStock] = useState<Record<string, string>>({})
  const list = speakers

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Voices
        </CardTitle>
        <CardDescription>
          {list.length} speaker{list.length === 1 ? '' : 's'} detected. Keep the original voices or
          replace them with stock catalog voices.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ModeToggle
          value={useOriginal ? 'local' : 'byok'}
          onChange={(v) => setUseOriginal(v === 'local')}
          localLabel="Original voices"
          byokLabel="Replace with stock"
        />
        {useOriginal ? (
          <div className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <ShieldCheck className="size-4 shrink-0 text-primary" />
            <span>Cloning is labeled synthetic, prepends a spoken disclaimer, and is watermarked. Only clone voices you have consent to use.</span>
          </div>
        ) : (
          <ul className="space-y-2">
            {list.map((s) => {
              const choice = stock[s.speaker_id] ?? voices.data?.voices?.[0]?.id ?? 'af_heart'
              const selected = (voices.data?.voices ?? []).find((v) => v.id === choice)
              const gender = s.gender ?? 'unknown'
              return (
                <li
                  key={s.speaker_id}
                  className="flex flex-col gap-3 rounded-md border border-border p-3 sm:flex-row sm:items-center"
                >
                  <span className="sm:w-52">
                    <span className="block font-mono text-sm">{s.display_name ?? s.speaker_id}</span>
                    <span className="text-xs text-muted-foreground">
                      {gender} · {Math.round(s.speaking_seconds)}s speaking
                    </span>
                  </span>
                  <span className="flex min-w-0 flex-1 items-center gap-1 sm:ml-auto sm:max-w-xs">
                    <PlaySample voiceId={choice} name={selected?.name ?? choice} />
                    <Select
                      aria-label={`Stock voice for ${s.speaker_id}`}
                      value={choice}
                      onChange={(e) => setStock((p) => ({ ...p, [s.speaker_id]: e.target.value }))}
                    >
                      {(voices.data?.voices ?? []).map((v) => (
                        <option key={v.id} value={v.id}>
                          {stockVoiceLabel(v.name, v.gender)}
                        </option>
                      ))}
                    </Select>
                  </span>
                </li>
              )
            })}
          </ul>
        )}
        {!useOriginal && (
          <ul className="space-y-1 text-xs text-muted-foreground">
            {list.map((s) => (
              <li key={`g-${s.speaker_id}`}>
                {s.display_name ?? s.speaker_id}: {s.gender ?? 'unknown gender'}
              </li>
            ))}
          </ul>
        )}
        <WaitHint />
        <div className="flex justify-end">
          <Button
            variant="wave"
            disabled={cont.isPending || list.length === 0}
            onClick={() => {
              const voice_assignments = list.map((s) =>
                useOriginal
                  ? { speaker_id: s.speaker_id, mode: 'clone' as const }
                  : {
                      speaker_id: s.speaker_id,
                      mode: 'stock' as const,
                      stock_voice: stock[s.speaker_id] ?? voices.data?.voices?.[0]?.id ?? 'af_heart',
                    },
              )
              cont.mutate({
                gate: 'voices',
                payload: { use_original: useOriginal, voice_assignments },
              })
            }}
          >
            {cont.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Continue
          </Button>
        </div>
        {cont.isError && <p className="text-sm text-status-failed">Couldn&apos;t continue. Try again.</p>}
      </CardContent>
    </Card>
  )
}

function SummarizeGate({ jobId, info }: { jobId: string; info?: GateInfo }) {
  const cont = useContinueJob(jobId)
  const llm = useLlmSettings()
  const [smart, setSmart] = useState(false)
  const [minutes, setMinutes] = useState(30)
  const [mode, setMode] = useState<'local' | 'byok'>('byok')
  const [backend, setBackend] = useState(llm.data?.backend ?? 'openrouter')
  const [model, setModel] = useState(llm.data?.openrouter_model ?? info?.openrouter_llm_model ?? '')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-[18px] text-primary" /> Summarize
        </CardTitle>
        <CardDescription>Target length and which LLM writes the digest.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant={!smart ? 'default' : 'outline'} onClick={() => setSmart(false)}>
            Set minutes
          </Button>
          <Button type="button" variant={smart ? 'default' : 'outline'} onClick={() => setSmart(true)}>
            Smart decision
          </Button>
        </div>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Target length</span>
          <div className="flex items-center gap-2">
            <Input
              aria-label="Target minutes"
              type="number"
              min={1}
              disabled={smart}
              value={minutes}
              onChange={(e) => setMinutes(Number(e.target.value))}
              className="w-24"
            />
            <span className="text-sm text-muted-foreground">min</span>
          </div>
        </label>
        <ModeToggle value={mode} onChange={setMode} localLabel="Local · Ollama" byokLabel="BYOK · hosted" />
        {mode === 'local' ? (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Ollama model</span>
            <Input
              aria-label="Ollama model"
              value={model || info?.ollama_model || ''}
              onChange={(e) => setModel(e.target.value)}
            />
          </label>
        ) : (
          <>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Backend</span>
              <Select aria-label="LLM backend" value={backend} onChange={(e) => setBackend(e.target.value)}>
                <option value="openrouter">openrouter</option>
                <option value="anthropic">anthropic</option>
              </Select>
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Model</span>
              <Input aria-label="LLM model" value={model} onChange={(e) => setModel(e.target.value)} />
              <MissingKey
                missing={backend === 'openrouter'}
                configured={!!info?.openrouter_configured}
              />
            </label>
          </>
        )}
        <WaitHint />
        <div className="flex justify-end">
          <Button
            variant="wave"
            disabled={cont.isPending}
            onClick={() =>
              cont.mutate({
                gate: 'summarize',
                payload: {
                  length_mode: smart ? 'smart' : 'manual',
                  target_minutes: smart ? null : minutes,
                  mode,
                  backend: mode === 'byok' ? backend : 'ollama',
                  model,
                },
              })
            }
          >
            {cont.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Continue
          </Button>
        </div>
        {cont.isError && <p className="text-sm text-status-failed">Couldn&apos;t continue. Try again.</p>}
      </CardContent>
    </Card>
  )
}

function TtsGate({ jobId, info }: { jobId: string; info?: GateInfo }) {
  const cont = useContinueJob(jobId)
  const voices = useVoices()
  const [mode, setMode] = useState<'local' | 'byok'>('local')
  const [model, setModel] = useState(info?.openrouter_tts_model ?? 'fish-audio/s2.1-pro')
  const [narrator, setNarrator] = useState(voices.data?.voices?.[0]?.id ?? 'af_heart')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Text to speech
        </CardTitle>
        <CardDescription>Synthesize the script locally or with OpenRouter speech.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ModeToggle value={mode} onChange={setMode} localLabel="Local · Kokoro / F5" byokLabel="BYOK · OpenRouter" />
        {mode === 'byok' && (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Speech model</span>
            <Input aria-label="TTS model" value={model} onChange={(e) => setModel(e.target.value)} />
            <MissingKey missing configured={!!info?.openrouter_configured} />
          </label>
        )}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Narrator stock voice</span>
          <p className="text-xs text-muted-foreground">
            Used for a single-narrator digest. Ignored when speakers keep original or stock assignments.
          </p>
          <Select aria-label="Narrator voice" value={narrator} onChange={(e) => setNarrator(e.target.value)}>
            {(voices.data?.voices ?? []).map((v) => (
              <option key={v.id} value={v.id}>
                {stockVoiceLabel(v.name, v.gender)}
              </option>
            ))}
          </Select>
        </label>
        <WaitHint />
        <div className="flex justify-end">
          <Button
            variant="wave"
            disabled={cont.isPending || (mode === 'byok' && !info?.openrouter_configured)}
            onClick={() =>
              cont.mutate({
                gate: 'tts',
                payload: { mode, model: mode === 'byok' ? model : undefined, narrator_voice: narrator },
              })
            }
          >
            {cont.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} Continue
          </Button>
        </div>
        {cont.isError && <p className="text-sm text-status-failed">Couldn&apos;t continue. Try again.</p>}
      </CardContent>
    </Card>
  )
}
