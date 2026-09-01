import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { JobDetail } from './JobDetail'

function renderAt(id: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/jobs/${id}`]}>
        <Routes>
          <Route path="/jobs/:id" element={<JobDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('JobDetail', () => {
  it('shows result and chapters when completed', async () => {
    server.use(
      http.get('/jobs/j1', () =>
        HttpResponse.json({
          id: 'j1',
          status: 'completed',
          current_stage: null,
          stages: [{ stage: 'assemble', state: 'done', detail: null, started_at: null, finished_at: null }],
          report: {},
        }),
      ),
      http.get('/jobs/j1/result', () =>
        HttpResponse.json({
          audio_mp3_url: '/jobs/j1/audio?format=mp3',
          audio_wav_url: '/jobs/j1/audio?format=wav',
          summary: 'the story',
          chapters: [{ title: 'Intro', start_s: 0 }],
        }),
      ),
    )
    renderAt('j1')
    await waitFor(() => expect(screen.getByText('the story')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /intro/i })).toBeInTheDocument()
  })

  it('shows live download detail on a running job', async () => {
    server.use(
      http.get('/jobs/j-run', () =>
        HttpResponse.json({
          id: 'j-run',
          status: 'running',
          current_stage: 'download',
          stages: [
            {
              stage: 'download',
              state: 'running',
              detail: 'Episode 1 · 1/3 · 42%',
              started_at: new Date().toISOString(),
              finished_at: null,
            },
          ],
          report: {},
        }),
      ),
    )
    renderAt('j-run')
    await waitFor(() => expect(screen.getAllByText(/42%/).length).toBeGreaterThanOrEqual(2))
    expect(screen.getByText('Download')).toBeInTheDocument()
  })

  it('shows this job elapsed from resolve start, treating naive UTC as UTC', async () => {
    const started = new Date(Date.now() - 12_000).toISOString().replace(/Z$/, '')
    server.use(
      http.get('/jobs/j-elapsed', () =>
        HttpResponse.json({
          id: 'j-elapsed',
          status: 'running',
          current_stage: 'resolve',
          stages: [
            {
              stage: 'resolve',
              state: 'running',
              detail: 'fetching feed',
              started_at: started,
              finished_at: null,
            },
          ],
          report: {},
        }),
      ),
    )
    renderAt('j-elapsed')
    await waitFor(() => expect(screen.getAllByText(/12s|13s|11s/).length).toBeGreaterThanOrEqual(1))
    expect(screen.queryByText(/210m/)).not.toBeInTheDocument()
  })

  it('shows the transcribe gate when a job is awaiting config', async () => {
    server.use(
      http.get('/jobs/j2', () =>
        HttpResponse.json({
          id: 'j2',
          status: 'awaiting_config',
          current_stage: 'download',
          gate: 'transcribe',
          stages: [{ stage: 'download', state: 'done', detail: null, started_at: null, finished_at: null }],
          report: { gate: 'transcribe' },
          gate_info: { openrouter_configured: true, whisper_model: 'small' },
        }),
      ),
    )
    renderAt('j2')
    await waitFor(() => expect(screen.getByText(/run speech-to-text/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /local/i })).toBeInTheDocument()
  })
})
