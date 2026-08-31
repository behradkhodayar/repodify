import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { server } from '../test/msw'
import { PodcastSearch } from './PodcastSearch'

const HIT = {
  title: 'Linear Digressions',
  author: 'Katie & Ben',
  feed_url: 'https://feeds.example.com/ld.xml',
  artwork: null,
  itunes_id: 941219323,
  pi_feed_id: null,
  newest_item: Math.floor(Date.now() / 1000) - 3 * 24 * 3600,
  episode_count: 400,
  language: 'en',
  sources: ['itunes'],
  identity: 'itunes:941219323',
  cached: false,
  dead: false,
}

function Harness({ onSelect = vi.fn() }: { onSelect?: (c: unknown) => void }) {
  const [value, setValue] = useState('')
  return (
    <PodcastSearch value={value} onChange={setValue} onSelect={onSelect} debounceMs={0} />
  )
}

describe('PodcastSearch', () => {
  it('does not search below three characters', async () => {
    const spy = vi.fn()
    server.use(
      http.get('/feeds/search', () => {
        spy()
        return HttpResponse.json({
          query: 'ab',
          kind: 'name',
          candidates: [],
          degraded: false,
          cached: false,
          warning: null,
        })
      }),
    )
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByLabelText(/podcast name or rss url/i), 'ab')
    await new Promise((r) => setTimeout(r, 20))
    expect(spy).not.toHaveBeenCalled()
  })

  it('lists matches and selects on click without auto-picking a single hit', async () => {
    const onSelect = vi.fn()
    server.use(
      http.get('/feeds/search', () =>
        HttpResponse.json({
          query: 'Linear Digressions',
          kind: 'name',
          candidates: [HIT],
          degraded: false,
          cached: false,
          warning: null,
        }),
      ),
    )
    const user = userEvent.setup()
    render(<Harness onSelect={onSelect} />)
    await user.type(screen.getByLabelText(/podcast name or rss url/i), 'Linear Digressions')
    await waitFor(() => expect(screen.getByText('Linear Digressions')).toBeInTheDocument())
    expect(screen.getByText(/katie & ben/i)).toBeInTheDocument()
    expect(onSelect).not.toHaveBeenCalled()
    await user.click(screen.getByRole('option', { name: /linear digressions/i }))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ feed_url: HIT.feed_url }))
  })

  it('shows empty copy and a paste-URL action', async () => {
    server.use(
      http.get('/feeds/search', () =>
        HttpResponse.json({
          query: 'zzzz-no-show',
          kind: 'name',
          candidates: [],
          degraded: false,
          cached: false,
          warning: null,
        }),
      ),
    )
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByLabelText(/podcast name or rss url/i), 'zzzz-no-show')
    await waitFor(() => expect(screen.getByText(/no public listing found/i)).toBeInTheDocument())
    expect(screen.getAllByText(/paste an rss url/i).length).toBeGreaterThan(0)
  })
})
