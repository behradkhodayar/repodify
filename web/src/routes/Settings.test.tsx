import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { Settings } from './Settings'

const LLM = {
  backend: 'anthropic',
  openrouter_model: 'openai/gpt-4o-mini',
  ollama_model: 'qwen2.5-coder:7b',
  anthropic_map_model: 'claude-haiku-4-5-20251001',
  anthropic_reduce_model: 'claude-opus-4-8',
  available_backends: ['anthropic', 'ollama', 'openrouter'],
  openrouter_configured: true,
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
    http.get('/settings/llm', () => HttpResponse.json(LLM)),
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
  it('keeps LLM and voice cards visible when their APIs fail', async () => {
    server.use(
      http.get('/settings/llm', () => new HttpResponse('nope', { status: 401 })),
      http.get('/voices', () => new HttpResponse('nope', { status: 401 })),
      http.get('/settings/voices', () => new HttpResponse('nope', { status: 401 })),
    )
    renderPage()
    await waitFor(() => expect(screen.getByText(/summarization llm/i)).toBeInTheDocument())
    expect(screen.getByText(/preferred stock voices/i)).toBeInTheDocument()
    expect(screen.getAllByText(/couldn't load/i).length).toBeGreaterThan(0)
  })

  it('saves the token to localStorage', async () => {
    stubSettingsApis()
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })

  it('selects the openrouter backend + model and saves it', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/voices', () => HttpResponse.json(VOICES)),
      http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
      http.get('/settings/llm', () => HttpResponse.json(LLM)),
      http.put('/settings/llm', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json({ ...LLM, backend: 'openrouter', openrouter_model: 'x/y' })
      }),
    )
    const user = userEvent.setup()
    renderPage()
    // Wait for the card to hydrate from the GET.
    await waitFor(() => expect(screen.getByLabelText(/llm backend/i)).toHaveValue('anthropic'))
    await user.selectOptions(screen.getByLabelText(/llm backend/i), 'openrouter')
    const model = screen.getByLabelText(/^model$/i)
    await user.clear(model)
    await user.type(model, 'x/y')
    await user.click(screen.getByRole('button', { name: /save llm settings/i }))
    await waitFor(() =>
      expect(putBody).toEqual({ backend: 'openrouter', openrouter_model: 'x/y', ollama_model: 'qwen2.5-coder:7b' }),
    )
  })

  it('saves preferred stock voices with gender-tagged names', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/settings/llm', () => HttpResponse.json(LLM)),
      http.get('/voices', () => HttpResponse.json(VOICES)),
      http.get('/settings/voices', () => HttpResponse.json({ preferred_stock_voices: [] })),
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
