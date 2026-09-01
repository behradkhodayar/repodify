import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { JobStatusResponse } from '../api/types'
import { server } from '../test/msw'
import { StageGates } from './StageGates'

function renderGate(job: JobStatusResponse) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <StageGates job={job} />
    </QueryClientProvider>,
  )
}

const base = (over: Partial<JobStatusResponse>): JobStatusResponse => ({
  id: 'j1',
  status: 'awaiting_config',
  current_stage: null,
  stages: [],
  report: {},
  gate_info: { openrouter_configured: true, whisper_model: 'small' },
  ...over,
})

describe('StageGates', () => {
  it('submits local transcribe config', async () => {
    let body: { gate?: string; payload?: { mode?: string; model?: string } } | null = null
    server.use(
      http.post('/jobs/j1/continue', async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json({ job_id: 'j1' })
      }),
    )
    const user = userEvent.setup()
    renderGate(base({ gate: 'transcribe' }))
    expect(screen.getByText(/you can close this page/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /continue/i }))
    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.gate).toBe('transcribe')
    expect(body!.payload?.mode).toBe('local')
    expect(body!.payload?.model).toBe('small')
  })

  it('disables minutes when smart decision is selected', async () => {
    server.use(
      http.get('/settings/llm', () =>
        HttpResponse.json({
          backend: 'openrouter',
          openrouter_model: 'openai/gpt-4o-mini',
          ollama_model: 'qwen2.5-coder:7b',
          anthropic_map_model: 'x',
          anthropic_reduce_model: 'y',
          available_backends: ['openrouter', 'ollama', 'anthropic'],
          openrouter_configured: true,
        }),
      ),
    )
    renderGate(base({ gate: 'summarize' }))
    const minutes = screen.getByLabelText(/target minutes/i)
    expect(minutes).not.toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /smart decision/i }))
    expect(minutes).toBeDisabled()
  })
})
