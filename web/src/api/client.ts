import type {
  CreateJobRequest,
  JobListResponse,
  JobStatusResponse,
  ResolveResponse,
  ResultResponse,
  SpeakersResponse,
  SubmitVoicesRequest,
  VoicesResponse,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('api_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Same-origin API. Resolve against location.origin so both the browser and the
// jsdom test runner (Node fetch, which needs an absolute URL) work.
function apiUrl(path: string): string {
  const origin = typeof location !== 'undefined' ? location.origin : ''
  return `${origin}${path}`
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(apiUrl(path), {
    ...init,
    headers: { 'content-type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!resp.ok) throw new ApiError(resp.status, await resp.text())
  return (await resp.json()) as T
}

export const api = {
  resolveFeed: (url: string) =>
    apiFetch<ResolveResponse>('/feeds/resolve', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  createJob: (body: CreateJobRequest) =>
    apiFetch<{ job_id: string }>('/jobs', { method: 'POST', body: JSON.stringify(body) }),
  getJobs: (limit = 50, offset = 0) =>
    apiFetch<JobListResponse>(`/jobs?limit=${limit}&offset=${offset}`),
  getJob: (id: string) => apiFetch<JobStatusResponse>(`/jobs/${id}`),
  getResult: (id: string) => apiFetch<ResultResponse>(`/jobs/${id}/result`),
  getVoices: () => apiFetch<VoicesResponse>('/voices'),
  getSpeakers: (id: string) => apiFetch<SpeakersResponse>(`/jobs/${id}/speakers`),
  submitVoices: (id: string, body: SubmitVoicesRequest) =>
    apiFetch<{ job_id: string }>(`/jobs/${id}/voices`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
