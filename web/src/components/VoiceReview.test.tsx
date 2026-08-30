import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { VoiceReview } from './VoiceReview'

function renderReview(id = 'j1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <VoiceReview jobId={id} />
    </QueryClientProvider>,
  )
}

describe('VoiceReview', () => {
  it('lists detected speakers and submits per-speaker voice assignments', async () => {
    let posted: { voice_assignments: unknown } | null = null
    server.use(
      http.get('/jobs/j1/speakers', () =>
        HttpResponse.json({
          status: 'awaiting_review',
          speakers: [
            { speaker_id: 'SPEAKER_00', speaking_seconds: 42, display_name: null },
            { speaker_id: 'SPEAKER_01', speaking_seconds: 30, display_name: null },
          ],
        }),
      ),
      http.get('/voices', () =>
        HttpResponse.json({
          stock_voices: ['af_heart', 'am_adam'],
          voices: [
            { id: 'af_heart', name: 'Heart', gender: 'female', sample_url: '/voices/af_heart/sample' },
            { id: 'am_adam', name: 'Adam', gender: 'male', sample_url: '/voices/am_adam/sample' },
          ],
        }),
      ),
      http.post('/jobs/j1/voices', async ({ request }) => {
        posted = (await request.json()) as { voice_assignments: unknown }
        return HttpResponse.json({ job_id: 'j1' })
      }),
    )

    renderReview()
    await waitFor(() => expect(screen.getByText('SPEAKER_00')).toBeInTheDocument())

    const select = screen.getByLabelText('Voice for SPEAKER_01') as HTMLSelectElement
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      'Clone this speaker',
      'Stock: Heart (female)',
      'Stock: Adam (male)',
    ])

    // Assign a stock voice to the second speaker; leave the first as clone (default).
    fireEvent.change(select, {
      target: { value: 'af_heart' },
    })
    expect(screen.getByRole('button', { name: /play sample of heart/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /generate digest/i }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted!.voice_assignments).toEqual([
      { speaker_id: 'SPEAKER_00', mode: 'clone' },
      { speaker_id: 'SPEAKER_01', mode: 'stock', stock_voice: 'af_heart' },
    ])
  })
})
