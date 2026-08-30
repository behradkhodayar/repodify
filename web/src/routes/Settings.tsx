import { Check, Cpu, KeyRound, Mic, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  useLlmSettings,
  useUpdateLlmSettings,
  useUpdateVoiceSettings,
  useVoiceSettings,
  useVoices,
} from '../api/queries'
import { PageHeader } from '../components/PageHeader'
import { StockVoiceList } from '../components/StockVoiceList'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { useToken } from '../lib/useToken'

export function Settings() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  const [saved, setSaved] = useState(false)

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader title="Settings" description="Configure how the web client talks to the cutcast API." />
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
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">API token</span>
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
          </label>
          <div className="flex items-center gap-3">
            <Button
              onClick={() => {
                setToken(value)
                setSaved(true)
              }}
            >
              <Save /> Save
            </Button>
            {saved && (
              <span className="flex items-center gap-1.5 text-sm text-status-done">
                <Check className="size-4" /> Saved
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <LlmCard />
      <VoicesCard />
    </div>
  )
}

function LlmCard() {
  const { data } = useLlmSettings()
  const update = useUpdateLlmSettings()
  const [backend, setBackend] = useState('anthropic')
  const [openrouterModel, setOpenrouterModel] = useState('')
  const [ollamaModel, setOllamaModel] = useState('')
  const [saved, setSaved] = useState(false)

  // Hydrate local form state once the server config loads.
  useEffect(() => {
    if (!data) return
    setBackend(data.backend)
    setOpenrouterModel(data.openrouter_model)
    setOllamaModel(data.ollama_model)
  }, [data])

  if (!data) return null

  const modelValue = backend === 'openrouter' ? openrouterModel : ollamaModel
  const setModelValue = backend === 'openrouter' ? setOpenrouterModel : setOllamaModel
  const editable = backend === 'openrouter' || backend === 'ollama'
  const needsKey = backend === 'openrouter' && !data.openrouter_configured

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-[18px] text-primary" /> Summarization LLM
        </CardTitle>
        <CardDescription>
          Pick which model summarizes episodes. Saved on the server; overrides the .env default.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">LLM backend</span>
          <select
            aria-label="LLM backend"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
            value={backend}
            onChange={(e) => {
              setBackend(e.target.value)
              setSaved(false)
            }}
          >
            {data.available_backends.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Model</span>
          <Input
            aria-label="Model"
            value={editable ? modelValue : `${data.anthropic_map_model} / ${data.anthropic_reduce_model}`}
            disabled={!editable}
            onChange={(e) => {
              setModelValue(e.target.value)
              setSaved(false)
            }}
            placeholder="e.g. openai/gpt-4o-mini"
          />
          {!editable && (
            <span className="text-xs text-muted-foreground">
              Anthropic uses MAP_MODEL / REDUCE_MODEL from .env.
            </span>
          )}
          {needsKey && (
            <span className="text-xs text-status-failed">Set OPENROUTER_API_KEY in .env to use OpenRouter.</span>
          )}
        </label>

        <div className="flex items-center gap-3">
          <Button
            disabled={update.isPending}
            onClick={() => {
              update.mutate(
                { backend, openrouter_model: openrouterModel, ollama_model: ollamaModel },
                { onSuccess: () => setSaved(true) },
              )
            }}
          >
            <Save /> Save LLM settings
          </Button>
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-status-done">
              <Check className="size-4" /> Saved
            </span>
          )}
        </div>
      </CardContent>
    </Card>
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
  if (!catalog.data || !saved.data) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="size-[18px] text-primary" /> Preferred stock voices
        </CardTitle>
        <CardDescription>
          Hear each catalog voice and pick the ones gender-matching should use when a
          speaker isn&apos;t cloned. Leave none selected to use the full catalog.
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
          {justSaved && (
            <span className="flex items-center gap-1.5 text-sm text-status-done">
              <Check className="size-4" /> Saved
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
