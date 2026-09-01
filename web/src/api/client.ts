import type {
  AppSettingsResponse,
  AppSettingsUpdate,
  ContinueJobRequest,
  CreateJobRequest,
  JobListResponse,
  JobStatusResponse,
  LlmSettingsResponse,
  LlmSettingsUpdate,
  ResolveResponse,
  ResultResponse,
  SearchResponse,
  SpeakersResponse,
  SubmitVoicesRequest,
  VoiceSettingsResponse,
  VoiceSettingsUpdate,
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
  searchFeeds: (q: string, signal?: AbortSignal) =>
    apiFetch<SearchResponse>(`/feeds/search?q=${encodeURIComponent(q)}`, { signal }),
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
  getVoiceSample: async (id: string) => {
    const resp = await fetch(apiUrl(`/voices/${id}/sample`), { headers: authHeaders() })
    if (!resp.ok) throw new ApiError(resp.status, await resp.text())
    return resp.blob()
  },
  getVoiceSettings: () => apiFetch<VoiceSettingsResponse>('/settings/voices'),
  updateVoiceSettings: (body: VoiceSettingsUpdate) =>
    apiFetch<VoiceSettingsResponse>('/settings/voices', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getSpeakers: (id: string) => apiFetch<SpeakersResponse>(`/jobs/${id}/speakers`),
  submitVoices: (id: string, body: SubmitVoicesRequest) =>
    apiFetch<{ job_id: string }>(`/jobs/${id}/voices`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  continueJob: (id: string, body: ContinueJobRequest) =>
    apiFetch<{ job_id: string }>(`/jobs/${id}/continue`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getLlmSettings: () => apiFetch<LlmSettingsResponse>('/settings/llm'),
  updateLlmSettings: (body: LlmSettingsUpdate) =>
    apiFetch<LlmSettingsResponse>('/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  getAppSettings: () => apiFetch<AppSettingsResponse>('/settings'),
  updateAppSettings: (body: AppSettingsUpdate) =>
    apiFetch<AppSettingsResponse>('/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
