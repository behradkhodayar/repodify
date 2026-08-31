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

const SEARCH = http.get('/feeds/search', () =>
  HttpResponse.json({
    query: 'https://x',
    kind: 'rss_url',
    candidates: [
      {
        title: 'https://x',
        author: '',
        feed_url: 'https://x',
        artwork: null,
        itunes_id: null,
        pi_feed_id: null,
        newest_item: null,
        episode_count: null,
        language: null,
        sources: ['url'],
        identity: 'url:https://x',
        cached: false,
        dead: false,
      },
    ],
    degraded: false,
    cached: false,
    warning: null,
  }),
)

const RESOLVE = http.post('/feeds/resolve', () =>
  HttpResponse.json({
    feed_title: 'Show',
    rss_url: 'https://x/rss',
    episodes: [
      { guid: 'e1', title: 'Ep One', published_at: null, duration_s: 60, order_index: 0, is_short_or_trailer: false },
    ],
  }),
)

describe('NewDigest', () => {
  it('resolves a feed, lists episodes, and creates a job', async () => {
    server.use(SEARCH, RESOLVE, http.post('/jobs', () => HttpResponse.json({ job_id: 'job-1' })))
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText(/podcast name or rss url/i), 'https://x')
    await waitFor(() => expect(screen.getByRole('option')).toBeInTheDocument(), { timeout: 3000 })
    await user.click(screen.getByRole('option'))
    await waitFor(() => expect(screen.getByText('Ep One')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    await user.click(screen.getByRole('button', { name: /create digest/i }))
    await waitFor(() => expect(screen.getByText(/job-1/)).toBeInTheDocument())
  })

  it('submits custom_prompt and per-episode episode_prompts', async () => {
    let body: {
      custom_prompt?: string
      episode_prompts?: Record<string, string>
      feed_url?: string
    } | null = null
    server.use(
      SEARCH,
      RESOLVE,
      http.post('/jobs', async ({ request }) => {
        body = (await request.json()) as typeof body
        return HttpResponse.json({ job_id: 'job-2' })
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText(/podcast name or rss url/i), 'https://x')
    await waitFor(() => expect(screen.getByRole('option')).toBeInTheDocument(), { timeout: 3000 })
    await user.click(screen.getByRole('option'))
    await waitFor(() => expect(screen.getByText('Ep One')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    await user.type(screen.getByLabelText(/custom instructions/i), 'skip sponsor reads')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    await user.type(screen.getByLabelText(/note for ep one/i), 'keep the interview')
    await user.click(screen.getByRole('button', { name: /create digest/i }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body!.custom_prompt).toBe('skip sponsor reads')
    expect(body!.episode_prompts).toEqual({ e1: 'keep the interview' })
    expect(body!.feed_url).toBe('https://x/rss')
  })
})
