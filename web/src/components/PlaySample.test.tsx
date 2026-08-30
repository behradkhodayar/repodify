import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { server } from '../test/msw'
import { PlaySample, resetVoiceSampleForTests } from './PlaySample'

class MockAudio {
  src: string
  play = vi.fn().mockResolvedValue(undefined)
  pause = vi.fn()
  onended: (() => void) | null = null
  constructor(src?: string) {
    this.src = src ?? ''
  }
}

function renderPlay(id = 'af_heart', name = 'Heart') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PlaySample voiceId={id} name={name} />
    </QueryClientProvider>,
  )
}

describe('PlaySample', () => {
  afterEach(() => {
    resetVoiceSampleForTests()
    vi.unstubAllGlobals()
  })

  it('fetches the voice sample and plays it', async () => {
    let fetched = 0
    server.use(
      http.get('/voices/af_heart/sample', () => {
        fetched += 1
        return new HttpResponse(new Uint8Array([82, 73, 70, 70]), {
          headers: { 'Content-Type': 'audio/wav' },
        })
      }),
    )
    vi.stubGlobal('Audio', MockAudio)
    const user = userEvent.setup()
    renderPlay()
    await user.click(screen.getByRole('button', { name: /play sample of heart/i }))
    await act(async () => {
      await Promise.resolve()
    })
    await waitFor(() => expect(fetched).toBe(1))
    expect(screen.getByRole('button', { name: /pause sample of heart/i })).toBeInTheDocument()
  })
})
