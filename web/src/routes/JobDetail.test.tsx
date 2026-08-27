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

  it('shows the voice review when a job is awaiting review', async () => {
    server.use(
      http.get('/jobs/j2', () =>
        HttpResponse.json({
          id: 'j2',
          status: 'awaiting_review',
          current_stage: 'diarize',
          stages: [{ stage: 'diarize', state: 'done', detail: null, started_at: null, finished_at: null }],
          report: {},
        }),
      ),
      http.get('/jobs/j2/speakers', () =>
        HttpResponse.json({
          status: 'awaiting_review',
          speakers: [{ speaker_id: 'SPEAKER_00', speaking_seconds: 10, display_name: null }],
        }),
      ),
      http.get('/voices', () => HttpResponse.json({ stock_voices: ['af_heart'] })),
    )
    renderAt('j2')
    await waitFor(() =>
      expect(screen.getByText(/assign a voice to each speaker/i)).toBeInTheDocument(),
    )
    expect(screen.getByLabelText('Voice for SPEAKER_00')).toBeInTheDocument()
  })
})
