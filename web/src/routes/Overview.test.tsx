import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { Overview } from './Overview'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Overview />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Overview', () => {
  it('places the brand mark next to the hero headline', async () => {
    server.use(http.get('/jobs', () => HttpResponse.json({ jobs: [], total: 0 })))
    const { container } = renderPage()
    await waitFor(() => expect(screen.getByText(/turn long feeds into tight listens/i)).toBeInTheDocument())
    const mark = container.querySelector(`img[src="${import.meta.env.BASE_URL}favicon.svg"]`)
    expect(mark).not.toBeNull()
  })
})
