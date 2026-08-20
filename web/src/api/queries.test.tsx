import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { makeWrapper } from '../test/query'
import { useJob, useJobs } from './queries'

describe('query hooks', () => {
  it('useJobs returns the list', async () => {
    server.use(
      http.get('/jobs', () =>
        HttpResponse.json({
          jobs: [
            { id: 'a', status: 'queued', current_stage: null, target_minutes: 30, created_at: '2026-01-01T00:00:00Z' },
          ],
          total: 1,
        }),
      ),
    )
    const { result } = renderHook(() => useJobs(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.data?.total).toBe(1))
  })

  it('useJob stops polling once completed', async () => {
    server.use(
      http.get('/jobs/j1', () =>
        HttpResponse.json({ id: 'j1', status: 'completed', current_stage: null, stages: [], report: {} }),
      ),
    )
    const { result } = renderHook(() => useJob('j1'), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.data?.status).toBe('completed'))
  })
})
