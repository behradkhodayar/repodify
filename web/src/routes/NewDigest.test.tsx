import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { NewDigest } from './NewDigest'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NewDigest />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NewDigest', () => {
  it('resolves a feed, lists episodes, and creates a job', async () => {
    server.use(
      http.post('/feeds/resolve', () =>
        HttpResponse.json({
          feed_title: 'Show',
          rss_url: 'https://x/rss',
          episodes: [
            { guid: 'e1', title: 'Ep One', published_at: null, duration_s: 60, order_index: 0, is_short_or_trailer: false },
          ],
        }),
      ),
      http.post('/jobs', () => HttpResponse.json({ job_id: 'job-1' })),
    )
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText(/feed url/i), 'https://x')
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    await waitFor(() => expect(screen.getByText('Ep One')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    await user.click(screen.getByRole('button', { name: /create digest/i }))
    await waitFor(() => expect(screen.getByText(/job-1/)).toBeInTheDocument())
  })
})
