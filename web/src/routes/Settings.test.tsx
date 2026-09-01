import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { Settings } from './Settings'

const APP = {
  whisper_model: 'small',
  whisper_models: ['tiny', 'base', 'small', 'medium', 'large-v3'],
  ollama_model: 'qwen2.5-coder:7b',
  ollama_base_url: 'http://localhost:11434',
  diarization_model: 'pyannote/speaker-diarization-community-1',
  hf_token_configured: false,
  openrouter_stt_model: 'openai/whisper-large-v3',
  openrouter_llm_model: 'openai/gpt-4o-mini',
  openrouter_tts_model: 'fish-audio/s2.1-pro',
  openrouter_configured: true,
  anthropic_map_model: 'claude-haiku-4-5-20251001',
  anthropic_reduce_model: 'claude-opus-4-8',
  anthropic_configured: false,
  pyannoteai_model: 'community-1',
  pyannoteai_configured: false,
}

const VOICES = {
  stock_voices: ['af_heart', 'am_adam'],
  voices: [
    { id: 'af_heart', name: 'Heart', gender: 'female', sample_url: '/voices/af_heart/sample' },
    { id: 'am_adam', name: 'Adam', gender: 'male', sample_url: '/voices/am_adam/sample' },
  ],
}

function stubSettingsApis() {
  server.use(
    http.get('/settings', () => HttpResponse.json(APP)),
    http.get('/voices', () => HttpResponse.json(VOICES)),
    http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
  )
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Settings />
    </QueryClientProvider>,
  )
}

describe('Settings', () => {
  it('splits runtime config into Local and BYOK columns', async () => {
    stubSettingsApis()
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Local' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'BYOK' })).toBeInTheDocument()
    expect(screen.getByLabelText(/whisper model/i)).toHaveValue('small')
    expect(screen.getByLabelText(/ollama model/i)).toHaveValue('qwen2.5-coder:7b')
    expect(screen.getByLabelText(/openrouter stt model/i)).toHaveValue('openai/whisper-large-v3')
    expect(screen.getByLabelText(/openrouter llm model/i)).toHaveValue('openai/gpt-4o-mini')
  })

  it('keeps Local, BYOK, and voice cards visible when their APIs fail', async () => {
    server.use(
      http.get('/settings', () => new HttpResponse('nope', { status: 401 })),
      http.get('/voices', () => new HttpResponse('nope', { status: 401 })),
      http.get('/settings/voices', () => new HttpResponse('nope', { status: 401 })),
    )
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Local' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'BYOK' })).toBeInTheDocument()
    expect(screen.getByText(/preferred stock voices/i)).toBeInTheDocument()
    expect(screen.getAllByText(/couldn't load/i).length).toBeGreaterThan(0)
  })

  it('saves the token to localStorage', async () => {
    stubSettingsApis()
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^save token$/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })

  it('saves local and BYOK models together', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/settings', () => HttpResponse.json(APP)),
      http.get('/voices', () => HttpResponse.json(VOICES)),
      http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
      http.put('/settings', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json({ ...APP, ...(putBody as object) })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByLabelText(/whisper model/i)).toHaveValue('small'))
    await user.selectOptions(screen.getByLabelText(/whisper model/i), 'base')
    const ollama = screen.getByLabelText(/ollama model/i)
    await user.clear(ollama)
    await user.type(ollama, 'llama3.1:8b')
    const llm = screen.getByLabelText(/openrouter llm model/i)
    await user.clear(llm)
    await user.type(llm, 'anthropic/claude-3.5-haiku')
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))
    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody).toEqual(
      expect.objectContaining({
        whisper_model: 'base',
        ollama_model: 'llama3.1:8b',
        openrouter_llm_model: 'anthropic/claude-3.5-haiku',
      }),
    )
  })

  it('sends a typed API key and never displays stored secrets', async () => {
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('/settings', () => HttpResponse.json({ ...APP, openrouter_configured: true })),
      http.get('/voices', () => HttpResponse.json(VOICES)),
      http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
      http.put('/settings', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...APP, openrouter_configured: true })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByLabelText(/openrouter api key/i)).toBeInTheDocument())
    expect(screen.queryByDisplayValue(/sk-/)).not.toBeInTheDocument()
    await user.type(screen.getByLabelText(/openrouter api key/i), 'sk-or-new')
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))
    await waitFor(() =>
      expect(putBody).toEqual(expect.objectContaining({ openrouter_api_key: 'sk-or-new' })),
    )
  })

  it('omits blank key fields so a save does not clear existing secrets', async () => {
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('/settings', () => HttpResponse.json({ ...APP, openrouter_configured: true })),
      http.get('/voices', () => HttpResponse.json(VOICES)),
      http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
      http.put('/settings', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(APP)
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByLabelText(/whisper model/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /save runtime settings/i }))
    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody).not.toHaveProperty('openrouter_api_key')
    expect(putBody).not.toHaveProperty('anthropic_api_key')
    expect(putBody).not.toHaveProperty('hf_token')
  })

  it('saves preferred stock voices with gender-tagged names', async () => {
    let putBody: unknown = null
    stubSettingsApis()
    server.use(
      http.put('/settings/voices', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json(putBody as { preferred_stock_voices: string[] })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(screen.getByText('Heart')).toBeInTheDocument())
    expect(screen.getByText('female')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /play sample of heart/i })).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /prefer adam \(male\)/i }))
    await user.click(screen.getByRole('button', { name: /save preferred voices/i }))
    await waitFor(() => expect(putBody).toEqual({ preferred_stock_voices: ['am_adam'] }))
  })
})
