import { Check, HardDrive, KeyRound, Mic, Save, Server } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import {
  useAppSettings,
  useUpdateAppSettings,
  useUpdateVoiceSettings,
  useVoiceSettings,
  useVoices,
} from '../api/queries'
import type { AppSettingsResponse, AppSettingsUpdate } from '../api/types'
import { PageHeader } from '../components/PageHeader'
import { StockVoiceList } from '../components/StockVoiceList'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Select } from '../components/ui/select'
import { Separator } from '../components/ui/separator'
import { useToken } from '../lib/useToken'

export function Settings() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Defaults for each pipeline stage. Pick local GPU adapters or hosted BYOK backends; jobs still choose local vs hosted at each gate."
      />
      <TokenCard />
      <RuntimeSettings />
      <VoicesCard />
    </div>
  )
}

function TokenCard() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  const [saved, setSaved] = useState(false)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-[18px] text-primary" /> API token
        </CardTitle>
        <CardDescription>
          Sent as a Bearer token with every request. Leave blank if the API is open.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label="API token">
          <Input
            aria-label="API token"
            type="password"
            value={value}
            onChange={(e) => {
              setValue(e.target.value)
              setSaved(false)
            }}
            placeholder="leave blank if the API is open"
          />
        </Field>
        <SaveRow
          label="Save token"
          saved={saved}
          onClick={() => {
            setToken(value)
            setSaved(true)
          }}
        />
      </CardContent>
    </Card>
  )
}

type FormState = {
  whisper_model: string
  ollama_model: string
  ollama_base_url: string
  diarization_model: string
  openrouter_stt_model: string
  openrouter_llm_model: string
  openrouter_tts_model: string
  map_model: string
  reduce_model: string
  pyannoteai_model: string
  openrouter_api_key: string
  anthropic_api_key: string
  pyannoteai_api_key: string
  hf_token: string
}

const EMPTY: FormState = {
  whisper_model: 'small',
  ollama_model: '',
  ollama_base_url: '',
  diarization_model: '',
  openrouter_stt_model: '',
  openrouter_llm_model: '',
  openrouter_tts_model: '',
  map_model: '',
  reduce_model: '',
  pyannoteai_model: '',
  openrouter_api_key: '',
  anthropic_api_key: '',
  pyannoteai_api_key: '',
  hf_token: '',
}

function fromResponse(data: AppSettingsResponse): FormState {
  return {
    ...EMPTY,
    whisper_model: data.whisper_model,
    ollama_model: data.ollama_model,
    ollama_base_url: data.ollama_base_url,
    diarization_model: data.diarization_model,
    openrouter_stt_model: data.openrouter_stt_model,
    openrouter_llm_model: data.openrouter_llm_model,
    openrouter_tts_model: data.openrouter_tts_model,
    map_model: data.anthropic_map_model,
    reduce_model: data.anthropic_reduce_model,
    pyannoteai_model: data.pyannoteai_model,
  }
}

function RuntimeSettings() {
  const { data, isError } = useAppSettings()
  const update = useUpdateAppSettings()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!data) return
    setForm(fromResponse(data))
  }, [data])

  function patch(partial: Partial<FormState>) {
    setForm((prev) => ({ ...prev, ...partial }))
    setSaved(false)
  }

  function save() {
    const body: AppSettingsUpdate = {
      whisper_model: form.whisper_model,
      ollama_model: form.ollama_model,
      ollama_base_url: form.ollama_base_url,
      diarization_model: form.diarization_model,
      openrouter_stt_model: form.openrouter_stt_model,
      openrouter_llm_model: form.openrouter_llm_model,
      openrouter_tts_model: form.openrouter_tts_model,
      map_model: form.map_model,
      reduce_model: form.reduce_model,
      pyannoteai_model: form.pyannoteai_model,
    }
    if (form.openrouter_api_key.trim()) body.openrouter_api_key = form.openrouter_api_key.trim()
    if (form.anthropic_api_key.trim()) body.anthropic_api_key = form.anthropic_api_key.trim()
    if (form.pyannoteai_api_key.trim()) body.pyannoteai_api_key = form.pyannoteai_api_key.trim()
    if (form.hf_token.trim()) body.hf_token = form.hf_token.trim()
    update.mutate(body, {
      onSuccess: () => {
        setForm((prev) => ({
          ...prev,
          openrouter_api_key: '',
          anthropic_api_key: '',
          pyannoteai_api_key: '',
          hf_token: '',
        }))
        setSaved(true)
      },
    })
  }

  if (isError) {
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <LoadError title="Local" icon={<HardDrive className="size-[18px] text-primary" />} />
        <LoadError title="BYOK" icon={<Server className="size-[18px] text-primary" />} />
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-4">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HardDrive className="size-[18px] text-primary" />
              <h2 id="local-heading" className="text-lg font-semibold">
                Local
              </h2>
            </CardTitle>
            <CardDescription>On this machine. Faster-whisper, pyannote, Ollama, Kokoro/F5.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Stage title="Speech-to-text">
              <Field label="Whisper model">
                <Select
                  aria-label="Whisper model"
                  value={form.whisper_model}
                  onChange={(e) => patch({ whisper_model: e.target.value })}
                >
                  {data.whisper_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </Select>
              </Field>
            </Stage>
            <Separator />
            <Stage title="Diarization">
              <KeyField
                label="Hugging Face token"
                ariaLabel="Hugging Face token"
                configured={data.hf_token_configured}
                value={form.hf_token}
                onChange={(hf_token) => patch({ hf_token })}
              />
              <Field label="pyannote model">
                <Input
                  aria-label="Local diarization model"
                  value={form.diarization_model}
                  onChange={(e) => patch({ diarization_model: e.target.value })}
                />
              </Field>
            </Stage>
            <Separator />
            <Stage title="Summarization">
              <Field label="Ollama model">
                <Input
                  aria-label="Ollama model"
                  value={form.ollama_model}
                  onChange={(e) => patch({ ollama_model: e.target.value })}
                  placeholder="qwen2.5-coder:7b"
                />
              </Field>
              <Field label="Ollama URL">
                <Input
                  aria-label="Ollama URL"
                  value={form.ollama_base_url}
                  onChange={(e) => patch({ ollama_base_url: e.target.value })}
                />
              </Field>
            </Stage>
            <Separator />
            <Stage title="Text to speech">
              <p className="text-sm text-muted-foreground">
                Kokoro for stock catalog voices, F5-TTS for clones. No extra model id.
              </p>
            </Stage>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="size-[18px] text-primary" />
              <h2 id="byok-heading" className="text-lg font-semibold">
                BYOK
              </h2>
            </CardTitle>
            <CardDescription>Your keys. OpenRouter, Anthropic, and pyannoteAI.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Stage title="Shared key">
              <KeyField
                label="OpenRouter API key"
                ariaLabel="OpenRouter API key"
                configured={data.openrouter_configured}
                value={form.openrouter_api_key}
                onChange={(openrouter_api_key) => patch({ openrouter_api_key })}
                hint="Used for hosted STT, LLM, and TTS."
              />
            </Stage>
            <Separator />
            <Stage title="Speech-to-text">
              <Field label="OpenRouter STT model">
                <Input
                  aria-label="OpenRouter STT model"
                  value={form.openrouter_stt_model}
                  onChange={(e) => patch({ openrouter_stt_model: e.target.value })}
                />
              </Field>
            </Stage>
            <Separator />
            <Stage title="Diarization">
              <KeyField
                label="pyannoteAI API key"
                ariaLabel="pyannoteAI API key"
                configured={data.pyannoteai_configured}
                value={form.pyannoteai_api_key}
                onChange={(pyannoteai_api_key) => patch({ pyannoteai_api_key })}
              />
              <Field label="pyannoteAI model">
                <Input
                  aria-label="pyannoteAI model"
                  value={form.pyannoteai_model}
                  onChange={(e) => patch({ pyannoteai_model: e.target.value })}
                />
              </Field>
            </Stage>
            <Separator />
            <Stage title="Summarization">
              <Field label="OpenRouter LLM model">
                <Input
                  aria-label="OpenRouter LLM model"
                  value={form.openrouter_llm_model}
                  onChange={(e) => patch({ openrouter_llm_model: e.target.value })}
                />
              </Field>
              <KeyField
                label="Anthropic API key"
                ariaLabel="Anthropic API key"
                configured={data.anthropic_configured}
                value={form.anthropic_api_key}
                onChange={(anthropic_api_key) => patch({ anthropic_api_key })}
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Map model">
                  <Input
                    aria-label="Anthropic map model"
                    value={form.map_model}
                    onChange={(e) => patch({ map_model: e.target.value })}
                  />
                </Field>
                <Field label="Reduce model">
                  <Input
                    aria-label="Anthropic reduce model"
                    value={form.reduce_model}
                    onChange={(e) => patch({ reduce_model: e.target.value })}
                  />
                </Field>
              </div>
            </Stage>
            <Separator />
            <Stage title="Text to speech">
              <Field label="OpenRouter TTS model">
                <Input
                  aria-label="OpenRouter TTS model"
                  value={form.openrouter_tts_model}
                  onChange={(e) => patch({ openrouter_tts_model: e.target.value })}
                />
              </Field>
            </Stage>
          </CardContent>
        </Card>
      </div>
      <div className="flex items-center gap-3">
        <Button disabled={update.isPending} onClick={save}>
          <Save /> Save runtime settings
        </Button>
        {saved && <Saved />}
        {update.isError && (
          <span className="text-sm text-status-failed">Couldn&apos;t save. Check the token and try again.</span>
        )}
      </div>
    </div>
  )
}

function VoicesCard() {
  const catalog = useVoices()
  const saved = useVoiceSettings()
  const update = useUpdateVoiceSettings()
  const [preferred, setPreferred] = useState<string[]>([])
  const [justSaved, setJustSaved] = useState(false)

  useEffect(() => {
    if (!saved.data) return
    setPreferred(saved.data.preferred_stock_voices)
  }, [saved.data])

  const voices = catalog.data?.voices ?? []
  if (catalog.isError || saved.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="size-[18px] text-primary" /> Preferred stock voices
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-status-failed">
            Couldn&apos;t load voice settings. If the API requires a token, save it above.
          </p>
        </CardContent>
      </Card>
    )
  }
  if (!catalog.data || !saved.data) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Preferred stock voices
        </CardTitle>
        <CardDescription>
          Hear each catalog voice and pick the ones gender-matching should use when a speaker
          isn&apos;t cloned. Leave none selected to use the full catalog.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StockVoiceList voices={voices} preferredIds={preferred} onPreferredChange={setPreferred} />
        <div className="flex items-center gap-3">
          <Button
            disabled={update.isPending}
            onClick={() => {
              update.mutate(
                { preferred_stock_voices: preferred },
                { onSuccess: () => setJustSaved(true) },
              )
            }}
          >
            <Save /> Save preferred voices
          </Button>
          {justSaved && <Saved />}
        </div>
      </CardContent>
    </Card>
  )
}

function LoadError({ title, icon }: { title: string; icon: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {icon}
          <h2 className="text-lg font-semibold">{title}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-status-failed">
          Couldn&apos;t load settings. If the API requires a token, save it above.
        </p>
      </CardContent>
    </Card>
  )
}

function Stage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</h3>
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </div>
  )
}

function KeyField({
  label,
  ariaLabel,
  configured,
  value,
  onChange,
  hint,
}: {
  label: string
  ariaLabel: string
  configured: boolean
  value: string
  onChange: (value: string) => void
  hint?: string
}) {
  return (
    <label className="block space-y-1.5">
      <span className="flex items-center gap-2 text-sm font-medium">
        {label}
        <Badge variant={configured ? 'done' : 'idle'}>{configured ? 'set' : 'not set'}</Badge>
      </span>
      <Input
        aria-label={ariaLabel}
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={configured ? 'leave blank to keep current' : 'not set'}
        autoComplete="off"
      />
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  )
}

function SaveRow({ label, saved, onClick }: { label: string; saved: boolean; onClick: () => void }) {
  return (
    <div className="flex items-center gap-3">
      <Button onClick={onClick}>
        <Save /> {label}
      </Button>
      {saved && <Saved />}
    </div>
  )
}

function Saved() {
  return (
    <span className="flex items-center gap-1.5 text-sm text-status-done">
      <Check className="size-4" /> Saved
    </span>
  )
}
