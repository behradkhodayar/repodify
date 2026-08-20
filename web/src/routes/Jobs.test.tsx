import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { Jobs } from './Jobs'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Jobs />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Jobs', () => {
  it('lists jobs', async () => {
    server.use(
      http.get('/jobs', () =>
        HttpResponse.json({
          jobs: [
            { id: 'j9', status: 'completed', current_stage: null, target_minutes: 10, created_at: '2026-01-01T00:00:00Z' },
          ],
          total: 1,
        }),
      ),
    )
    renderPage()
    await waitFor(() => expect(screen.getByText(/j9/)).toBeInTheDocument())
    expect(screen.getByText(/completed/i)).toBeInTheDocument()
  })

  it('shows an empty state', async () => {
    server.use(http.get('/jobs', () => HttpResponse.json({ jobs: [], total: 0 })))
    renderPage()
    await waitFor(() => expect(screen.getByText(/no digests yet/i)).toBeInTheDocument())
  })
})
