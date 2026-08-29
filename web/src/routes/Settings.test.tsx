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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Settings />
    </QueryClientProvider>,
  )
}

describe('Settings', () => {
  it('saves the token to localStorage', async () => {
    server.use(http.get('/settings/llm', () => HttpResponse.json(LLM)))
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^save$/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })

  it('selects the openrouter backend + model and saves it', async () => {
    let putBody: unknown = null
    server.use(
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
})
