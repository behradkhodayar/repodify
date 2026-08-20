import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/msw'
import { ApiError, api } from './client'

describe('api client', () => {
  it('omits Authorization when no token is set', async () => {
    let auth: string | null = 'unset'
    server.use(
      http.get('/jobs', ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ jobs: [], total: 0 })
      }),
    )
    await api.getJobs()
    expect(auth).toBeNull()
  })

  it('sends Bearer token when set', async () => {
    localStorage.setItem('api_token', 'secret')
    let auth: string | null = null
    server.use(
      http.get('/jobs', ({ request }) => {
        auth = request.headers.get('authorization')
        return HttpResponse.json({ jobs: [], total: 0 })
      }),
    )
    await api.getJobs()
    expect(auth).toBe('Bearer secret')
  })

  it('throws ApiError with status on non-2xx', async () => {
    server.use(http.get('/jobs/x', () => new HttpResponse('nope', { status: 404 })))
    await expect(api.getJob('x')).rejects.toMatchObject({ status: 404 })
    await expect(api.getJob('x')).rejects.toBeInstanceOf(ApiError)
  })
})
