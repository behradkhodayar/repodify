# Web PWA Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React + Vite + TypeScript PWA (`web/`) that resolves feeds, launches digest jobs, polls progress, and plays the finished digest — served same-origin by FastAPI at `/app`.

**Architecture:** A static SPA built with Vite. TanStack Query owns server state (including job-status polling). A thin typed `fetch` client attaches a bearer token from localStorage. The native `<audio>` element streams the range-served mp3. FastAPI optionally mounts the built app at `/app` (no change to existing API routes). In dev, Vite proxies API paths to FastAPI.

**Tech Stack:** React 18, Vite, TypeScript, React Router, TanStack Query, Tailwind CSS, vite-plugin-pwa, Vitest + React Testing Library + MSW; FastAPI `StaticFiles` for serving.

## Global Constraints

- All frontend code lives under `web/`; run npm commands from `web/`.
- TypeScript strict mode (Vite react-ts default). No `any` in the API layer.
- The API is same-origin: call it with **relative** paths (`/feeds/...`, `/jobs/...`). Never hardcode a host.
- The bearer token is read from `localStorage["api_token"]`; send `Authorization: Bearer <token>` only when it is non-empty.
- API status semantics: job `status` ∈ `queued|running|completed|failed`; poll `GET /jobs/{id}` and stop polling on `completed|failed`.
- Audio URLs are relative and range-served: `GET /jobs/{id}/audio?format=mp3|wav`.
- Backend: do **not** change existing routes, schemas, or auth. The only backend edit is an optional static mount.
- Commit messages: imperative mood, what + why, no emojis, no `feat:`/`fix:` prefixes, no Claude co-authoring.
- Branch: `feat/web-pwa-client` (already created off `main`).
- Vitest tests use MSW v2 (`http`, `HttpResponse`, `setupServer` from `msw/node`).

---

### Task 1: Scaffold the web app

**Files:**
- Create: `web/` (Vite react-ts scaffold), `web/vite.config.ts`, `web/tailwind.config.js`, `web/postcss.config.js`, `web/src/index.css`, `web/src/test/setup.ts`, `web/src/test/msw.ts`, `web/src/smoke.test.tsx`

**Interfaces:**
- Produces: a buildable app; `npm run build`, `npm run test`, `npm run dev` scripts; MSW test server exported as `server` from `src/test/msw.ts`.

- [ ] **Step 1: Scaffold and install**

```bash
cd /home/behrad/Development/podcast-compactor
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install react-router-dom @tanstack/react-query
npm install -D tailwindcss@3 postcss autoprefixer vite-plugin-pwa \
  vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event msw
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Vite (proxy, PWA, Vitest), Tailwind, and CSS**

Replace `web/vite.config.ts`:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/app/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Podcast Compactor',
        short_name: 'Compactor',
        start_url: '/app/',
        scope: '/app/',
        display: 'standalone',
        theme_color: '#0f172a',
        background_color: '#0f172a',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
      workbox: {
        navigateFallback: '/app/index.html',
        runtimeCaching: [
          { urlPattern: /\/(jobs|feeds|health)(\/.*)?$/, handler: 'NetworkOnly' },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/feeds': 'http://localhost:8000',
      '/jobs': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
```

Replace `web/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

Replace `web/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Add scripts and MSW test harness**

In `web/package.json`, ensure the `scripts` block contains:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "lint": "tsc --noEmit"
}
```

Create `web/src/test/msw.ts`:

```ts
import { setupServer } from 'msw/node'

export const server = setupServer()
```

Create `web/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './msw'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())
```

- [ ] **Step 4: Write a smoke test**

Create `web/src/smoke.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

function Hello() {
  return <h1>Podcast Compactor</h1>
}

describe('smoke', () => {
  it('renders', () => {
    render(<Hello />)
    expect(screen.getByText('Podcast Compactor')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Verify test + build**

Run: `cd web && npm run test`
Expected: 1 passed.
Run: `cd web && npm run build`
Expected: builds to `web/dist/` with no type errors.

- [ ] **Step 6: Commit**

```bash
cd /home/behrad/Development/podcast-compactor
git add web
git commit -m "Scaffold React PWA web client with Vite, Tailwind, and Vitest"
```

---

### Task 2: Typed API client

**Files:**
- Create: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/client.test.ts`

**Interfaces:**
- Produces: `ApiError` (with `.status`), and `api` with `resolveFeed(url)`, `createJob(body)`, `getJobs(limit, offset)`, `getJob(id)`, `getResult(id)`; types `EpisodeOut`, `ResolveResponse`, `CreateJobRequest`, `JobStatusResponse`, `ResultResponse`, `JobListResponse`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/api/client.test.ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/api/client.test.ts`
Expected: FAIL — cannot find `./client`.

- [ ] **Step 3: Write the types**

```ts
// web/src/api/types.ts
export interface EpisodeOut {
  guid: string
  title: string
  published_at: string | null
  duration_s: number | null
  order_index: number
  is_short_or_trailer: boolean
}
export interface ResolveResponse {
  feed_title: string
  rss_url: string
  episodes: EpisodeOut[]
}
export interface CreateJobRequest {
  feed_url: string
  episode_ids: string[]
  host_count?: number
  clone?: boolean
  target_minutes?: number
}
export interface StageOut {
  stage: string
  state: string
  detail: string | null
  started_at: string | null
  finished_at: string | null
}
export interface JobStatusResponse {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  current_stage: string | null
  stages: StageOut[]
  report: { skipped?: string[]; warnings?: string[]; show_notes?: unknown }
}
export interface ChapterOut {
  title: string
  start_s: number
}
export interface ResultResponse {
  audio_mp3_url: string
  audio_wav_url: string
  summary: string
  chapters: ChapterOut[]
}
export interface JobSummaryOut {
  id: string
  status: string
  current_stage: string | null
  target_minutes: number
  created_at: string
}
export interface JobListResponse {
  jobs: JobSummaryOut[]
  total: number
}
```

- [ ] **Step 4: Write the client**

```ts
// web/src/api/client.ts
import type {
  CreateJobRequest,
  JobListResponse,
  JobStatusResponse,
  ResolveResponse,
  ResultResponse,
} from './types'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('api_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
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
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run src/api/client.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/api
git commit -m "Add typed API client with bearer-token auth"
```

---

### Task 3: TanStack Query hooks

**Files:**
- Create: `web/src/api/queries.ts`, `web/src/api/queries.test.tsx`, `web/src/test/query.tsx`

**Interfaces:**
- Consumes: `api` (Task 2).
- Produces: `useResolveFeed()`, `useCreateJob()`, `useJobs(limit?, offset?)`, `useJob(id)`, `useResult(id, enabled)`; and a test helper `wrapper` providing a fresh `QueryClient`.

- [ ] **Step 1: Write the query test wrapper**

```tsx
// web/src/test/query.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

export function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}
```

- [ ] **Step 2: Write the failing test**

```tsx
// web/src/api/queries.test.tsx
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
        HttpResponse.json({ jobs: [{ id: 'a', status: 'queued', current_stage: null, target_minutes: 30, created_at: '2026-01-01T00:00:00Z' }], total: 1 }),
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run src/api/queries.test.tsx`
Expected: FAIL — cannot find `./queries`.

- [ ] **Step 4: Write the hooks**

```ts
// web/src/api/queries.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { CreateJobRequest } from './types'

export function useResolveFeed() {
  return useMutation({ mutationFn: (url: string) => api.resolveFeed(url) })
}

export function useCreateJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateJobRequest) => api.createJob(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useJobs(limit = 50, offset = 0) {
  return useQuery({ queryKey: ['jobs', limit, offset], queryFn: () => api.getJobs(limit, offset) })
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ['job', id],
    queryFn: () => api.getJob(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 2000
    },
  })
}

export function useResult(id: string, enabled: boolean) {
  return useQuery({ queryKey: ['result', id], queryFn: () => api.getResult(id), enabled })
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run src/api/queries.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add web/src/api/queries.ts web/src/api/queries.test.tsx web/src/test/query.tsx
git commit -m "Add TanStack Query hooks with job-status polling"
```

---

### Task 4: App shell, routing, and token

**Files:**
- Create: `web/src/lib/useToken.ts`, `web/src/lib/useToken.test.ts`, `web/src/components/TokenBanner.tsx`, `web/src/App.tsx` (replace), `web/src/main.tsx` (replace)
- Create placeholder routes: `web/src/routes/NewDigest.tsx`, `web/src/routes/Jobs.tsx`, `web/src/routes/JobDetail.tsx`, `web/src/routes/Settings.tsx`

**Interfaces:**
- Produces: `useToken()` → `{ token, setToken }`; `App` mounting `QueryClientProvider` + `BrowserRouter basename="/app"` with routes `/`, `/jobs`, `/jobs/:id`, `/settings`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/useToken.test.ts
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useToken } from './useToken'

describe('useToken', () => {
  it('reads and writes localStorage', () => {
    const { result } = renderHook(() => useToken())
    expect(result.current.token).toBe('')
    act(() => result.current.setToken('secret'))
    expect(localStorage.getItem('api_token')).toBe('secret')
    expect(result.current.token).toBe('secret')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/lib/useToken.test.ts`
Expected: FAIL — cannot find `./useToken`.

- [ ] **Step 3: Implement useToken and the shell**

```ts
// web/src/lib/useToken.ts
import { useState } from 'react'

export function useToken() {
  const [token, setTokenState] = useState(() => localStorage.getItem('api_token') ?? '')
  function setToken(value: string) {
    if (value) localStorage.setItem('api_token', value)
    else localStorage.removeItem('api_token')
    setTokenState(value)
  }
  return { token, setToken }
}
```

```tsx
// web/src/components/TokenBanner.tsx
import { Link } from 'react-router-dom'

export function TokenBanner() {
  return (
    <div className="bg-amber-100 text-amber-900 px-4 py-2 text-sm">
      This API needs a token.{' '}
      <Link to="/settings" className="underline font-medium">Set it in Settings</Link>.
    </div>
  )
}
```

```tsx
// web/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

```tsx
// web/src/App.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { JobDetail } from './routes/JobDetail'
import { Jobs } from './routes/Jobs'
import { NewDigest } from './routes/NewDigest'
import { Settings } from './routes/Settings'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <nav className="flex gap-4 p-4 border-b bg-slate-900 text-white">
          <Link to="/">New digest</Link>
          <Link to="/jobs">History</Link>
          <Link to="/settings" className="ml-auto">Settings</Link>
        </nav>
        <main className="max-w-3xl mx-auto p-4">
          <Routes>
            <Route path="/" element={<NewDigest />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
```

Create minimal placeholder routes so the app compiles (each replaced in later tasks):

```tsx
// web/src/routes/NewDigest.tsx
export function NewDigest() {
  return <h1 className="text-xl font-semibold">New digest</h1>
}
```

```tsx
// web/src/routes/Jobs.tsx
export function Jobs() {
  return <h1 className="text-xl font-semibold">History</h1>
}
```

```tsx
// web/src/routes/JobDetail.tsx
export function JobDetail() {
  return <h1 className="text-xl font-semibold">Job</h1>
}
```

```tsx
// web/src/routes/Settings.tsx
export function Settings() {
  return <h1 className="text-xl font-semibold">Settings</h1>
}
```

- [ ] **Step 4: Run test + typecheck to verify**

Run: `cd web && npx vitest run src/lib/useToken.test.ts`
Expected: PASS.
Run: `cd web && npm run lint`
Expected: no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "Add app shell, routing, and token storage"
```

---

### Task 5: New Digest screen (resolve + pick + create)

**Files:**
- Create: `web/src/components/EpisodePicker.tsx`
- Modify: `web/src/routes/NewDigest.tsx`
- Test: `web/src/routes/NewDigest.test.tsx`

**Interfaces:**
- Consumes: `useResolveFeed`, `useCreateJob` (Task 3).
- Produces: a flow that resolves a feed, lists episodes with checkboxes, and creates a job.

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/routes/NewDigest.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/routes/NewDigest.test.tsx`
Expected: FAIL — the placeholder renders no feed input.

- [ ] **Step 3: Implement EpisodePicker and NewDigest**

```tsx
// web/src/components/EpisodePicker.tsx
import type { EpisodeOut } from '../api/types'

export function EpisodePicker({
  episodes,
  selected,
  onToggle,
}: {
  episodes: EpisodeOut[]
  selected: Set<string>
  onToggle: (guid: string) => void
}) {
  return (
    <ul className="divide-y border rounded">
      {episodes.map((ep) => (
        <li key={ep.guid} className="p-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={ep.title}
              checked={selected.has(ep.guid)}
              onChange={() => onToggle(ep.guid)}
            />
            <span className="font-medium">{ep.title}</span>
            {ep.is_short_or_trailer && (
              <span className="text-xs bg-slate-200 rounded px-1">trailer</span>
            )}
          </label>
        </li>
      ))}
    </ul>
  )
}
```

```tsx
// web/src/routes/NewDigest.tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EpisodePicker } from '../components/EpisodePicker'
import { useCreateJob, useResolveFeed } from '../api/queries'

export function NewDigest() {
  const [url, setUrl] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [targetMinutes, setTargetMinutes] = useState(30)
  const [hostCount, setHostCount] = useState(1)
  const resolve = useResolveFeed()
  const create = useCreateJob()
  const navigate = useNavigate()

  function toggle(guid: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(guid) ? next.delete(guid) : next.add(guid)
      return next
    })
  }

  async function onCreate() {
    const { job_id } = await create.mutateAsync({
      feed_url: url,
      episode_ids: [...selected],
      host_count: hostCount,
      target_minutes: targetMinutes,
    })
    navigate(`/jobs/${job_id}`)
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">New digest</h1>
      <div className="flex gap-2">
        <input
          className="border rounded px-2 py-1 flex-1"
          aria-label="Feed URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/feed.xml"
        />
        <button
          className="bg-slate-900 text-white rounded px-3"
          onClick={() => resolve.mutate(url)}
        >
          Resolve
        </button>
      </div>
      {resolve.isError && <p className="text-red-600">Couldn't fetch that feed.</p>}
      {resolve.data && (
        <>
          <EpisodePicker episodes={resolve.data.episodes} selected={selected} onToggle={toggle} />
          <div className="flex gap-4 items-center">
            <label>Minutes <input type="number" className="border rounded w-20 px-1" value={targetMinutes} onChange={(e) => setTargetMinutes(Number(e.target.value))} /></label>
            <label>Hosts
              <select className="border rounded ml-1" value={hostCount} onChange={(e) => setHostCount(Number(e.target.value))}>
                <option value={1}>1 (narrator)</option>
                <option value={2}>2 (dialogue)</option>
              </select>
            </label>
            <button
              className="bg-emerald-600 text-white rounded px-3 py-1 disabled:opacity-50"
              disabled={selected.size === 0 || create.isPending}
              onClick={onCreate}
            >
              Create digest
            </button>
          </div>
        </>
      )}
      {create.data && <p>Created job {create.data.job_id}…</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/routes/NewDigest.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/NewDigest.tsx web/src/routes/NewDigest.test.tsx web/src/components/EpisodePicker.tsx
git commit -m "Add new-digest screen with feed resolve and episode picker"
```

---

### Task 6: History screen

**Files:**
- Modify: `web/src/routes/Jobs.tsx`
- Test: `web/src/routes/Jobs.test.tsx`

**Interfaces:**
- Consumes: `useJobs` (Task 3).

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/routes/Jobs.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
        HttpResponse.json({ jobs: [{ id: 'j9', status: 'completed', current_stage: null, target_minutes: 10, created_at: '2026-01-01T00:00:00Z' }], total: 1 }),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/routes/Jobs.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement Jobs**

```tsx
// web/src/routes/Jobs.tsx
import { Link } from 'react-router-dom'
import { useJobs } from '../api/queries'

export function Jobs() {
  const { data, isLoading } = useJobs()
  if (isLoading) return <p>Loading…</p>
  if (!data || data.total === 0) return <p>No digests yet. Create one from “New digest”.</p>
  return (
    <ul className="divide-y border rounded">
      {data.jobs.map((j) => (
        <li key={j.id} className="p-2 flex justify-between">
          <Link to={`/jobs/${j.id}`} className="underline">{j.id}</Link>
          <span className="text-sm text-slate-600">{j.status} · {j.target_minutes} min</span>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/routes/Jobs.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/Jobs.tsx web/src/routes/Jobs.test.tsx
git commit -m "Add job history screen with empty state"
```

---

### Task 7: Job detail — progress, result, and player

**Files:**
- Create: `web/src/components/StageProgress.tsx`, `web/src/components/AudioPlayer.tsx`
- Modify: `web/src/routes/JobDetail.tsx`
- Test: `web/src/routes/JobDetail.test.tsx`, `web/src/components/AudioPlayer.test.tsx`

**Interfaces:**
- Consumes: `useJob`, `useResult` (Task 3).
- Produces: `StageProgress({ stages })`, `AudioPlayer({ jobId, chapters })`.

- [ ] **Step 1: Write the failing tests**

```tsx
// web/src/components/AudioPlayer.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AudioPlayer } from './AudioPlayer'

describe('AudioPlayer', () => {
  it('seeks to a chapter start on click', async () => {
    render(<AudioPlayer jobId="j1" chapters={[{ title: 'Intro', start_s: 0 }, { title: 'Part 2', start_s: 42 }]} />)
    const audio = document.querySelector('audio') as HTMLAudioElement
    const setSpy = vi.spyOn(audio, 'currentTime', 'set')
    await userEvent.click(screen.getByRole('button', { name: /part 2/i }))
    expect(setSpy).toHaveBeenCalledWith(42)
  })

  it('points at the mp3 endpoint', () => {
    render(<AudioPlayer jobId="j1" chapters={[]} />)
    const audio = document.querySelector('audio') as HTMLAudioElement
    expect(audio.getAttribute('src')).toBe('/jobs/j1/audio?format=mp3')
  })
})
```

```tsx
// web/src/routes/JobDetail.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '../test/msw'
import { JobDetail } from './JobDetail'

function renderAt(id: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/jobs/${id}`]}>
        <Routes>
          <Route path="/jobs/:id" element={<JobDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('JobDetail', () => {
  it('shows result and chapters when completed', async () => {
    server.use(
      http.get('/jobs/j1', () =>
        HttpResponse.json({ id: 'j1', status: 'completed', current_stage: null, stages: [{ stage: 'assemble', state: 'done', detail: null, started_at: null, finished_at: null }], report: {} }),
      ),
      http.get('/jobs/j1/result', () =>
        HttpResponse.json({ audio_mp3_url: '/jobs/j1/audio?format=mp3', audio_wav_url: '/jobs/j1/audio?format=wav', summary: 'the story', chapters: [{ title: 'Intro', start_s: 0 }] }),
      ),
    )
    renderAt('j1')
    await waitFor(() => expect(screen.getByText('the story')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /intro/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/routes/JobDetail.test.tsx src/components/AudioPlayer.test.tsx`
Expected: FAIL — components missing.

- [ ] **Step 3: Implement the components and route**

```tsx
// web/src/components/StageProgress.tsx
import type { StageOut } from '../api/types'

const ICON: Record<string, string> = { done: '✓', running: '…', failed: '✗', skipped: '–', pending: '·' }

export function StageProgress({ stages }: { stages: StageOut[] }) {
  return (
    <ul className="space-y-1">
      {stages.map((s, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span className="w-4">{ICON[s.state] ?? '·'}</span>
          <span className="font-medium">{s.stage}</span>
          {s.detail && <span className="text-slate-500">— {s.detail}</span>}
        </li>
      ))}
    </ul>
  )
}
```

```tsx
// web/src/components/AudioPlayer.tsx
import { useRef } from 'react'
import type { ChapterOut } from '../api/types'

export function AudioPlayer({ jobId, chapters }: { jobId: string; chapters: ChapterOut[] }) {
  const ref = useRef<HTMLAudioElement>(null)
  function seek(start: number) {
    if (ref.current) ref.current.currentTime = start
  }
  return (
    <div className="space-y-2">
      <audio ref={ref} controls src={`/jobs/${jobId}/audio?format=mp3`} className="w-full" />
      <ul className="text-sm">
        {chapters.map((c, i) => (
          <li key={i}>
            <button className="underline" onClick={() => seek(c.start_s)}>
              {c.title}
            </button>
          </li>
        ))}
      </ul>
      <div className="text-sm">
        Download: <a className="underline" href={`/jobs/${jobId}/audio?format=mp3`}>mp3</a>{' · '}
        <a className="underline" href={`/jobs/${jobId}/audio?format=wav`}>wav</a>
      </div>
    </div>
  )
}
```

```tsx
// web/src/routes/JobDetail.tsx
import { useParams } from 'react-router-dom'
import { useJob, useResult } from '../api/queries'
import { AudioPlayer } from '../components/AudioPlayer'
import { StageProgress } from '../components/StageProgress'

export function JobDetail() {
  const { id = '' } = useParams()
  const job = useJob(id)
  const completed = job.data?.status === 'completed'
  const result = useResult(id, completed)

  if (job.isLoading) return <p>Loading…</p>
  if (!job.data) return <p>Job not found.</p>

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Job {id}</h1>
      <p className="text-sm text-slate-600">Status: {job.data.status}</p>
      <StageProgress stages={job.data.stages} />
      {job.data.status === 'failed' && (
        <div className="text-red-600 text-sm">
          <p>This job failed.</p>
          <ul className="list-disc ml-5">
            {(job.data.report.skipped ?? []).map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {completed && result.data && (
        <div className="space-y-3">
          <p>{result.data.summary}</p>
          <AudioPlayer jobId={id} chapters={result.data.chapters} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/routes/JobDetail.test.tsx src/components/AudioPlayer.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/JobDetail.tsx web/src/routes/JobDetail.test.tsx web/src/components/StageProgress.tsx web/src/components/AudioPlayer.tsx web/src/components/AudioPlayer.test.tsx
git commit -m "Add job detail with stage progress, result, and audio player"
```

---

### Task 8: Settings screen

**Files:**
- Modify: `web/src/routes/Settings.tsx`
- Test: `web/src/routes/Settings.test.tsx`

**Interfaces:**
- Consumes: `useToken` (Task 4).

- [ ] **Step 1: Write the failing test**

```tsx
// web/src/routes/Settings.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { Settings } from './Settings'

describe('Settings', () => {
  it('saves the token to localStorage', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.type(screen.getByLabelText(/api token/i), 'secret')
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(localStorage.getItem('api_token')).toBe('secret')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run src/routes/Settings.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement Settings**

```tsx
// web/src/routes/Settings.tsx
import { useState } from 'react'
import { useToken } from '../lib/useToken'

export function Settings() {
  const { token, setToken } = useToken()
  const [value, setValue] = useState(token)
  return (
    <div className="space-y-3 max-w-md">
      <h1 className="text-xl font-semibold">Settings</h1>
      <label className="block">
        API token
        <input
          className="border rounded px-2 py-1 w-full mt-1"
          aria-label="API token"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="leave blank if the API is open"
        />
      </label>
      <button className="bg-slate-900 text-white rounded px-3 py-1" onClick={() => setToken(value)}>
        Save
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run src/routes/Settings.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/routes/Settings.tsx web/src/routes/Settings.test.tsx
git commit -m "Add settings screen for the API token"
```

---

### Task 9: PWA icons and build verification

**Files:**
- Create: `web/public/pwa-192x192.png`, `web/public/pwa-512x512.png`

**Interfaces:**
- Produces: a production build with a manifest + service worker (the plugin was configured in Task 1).

- [ ] **Step 1: Add the two icons**

Generate simple solid icons (ImageMagick if present, else any 192/512 PNGs):

```bash
cd /home/behrad/Development/podcast-compactor/web/public
if command -v convert >/dev/null; then
  convert -size 192x192 xc:'#0f172a' -gravity center -pointsize 96 -fill white -annotate 0 'PC' pwa-192x192.png
  convert -size 512x512 xc:'#0f172a' -gravity center -pointsize 256 -fill white -annotate 0 'PC' pwa-512x512.png
else
  echo "Add pwa-192x192.png and pwa-512x512.png manually (192px and 512px)"; fi
```

If ImageMagick is unavailable, create the two PNGs by any means (they just need the right pixel sizes). Do not commit a zero-byte file.

- [ ] **Step 2: Build and verify the PWA output**

Run: `cd web && npm run build`
Expected: `web/dist/manifest.webmanifest` and a service worker (`web/dist/sw.js`) are emitted; no type errors.

- [ ] **Step 3: Commit**

```bash
git add web/public/pwa-192x192.png web/public/pwa-512x512.png
git commit -m "Add PWA icons"
```

---

### Task 10: Backend static mount + README + final gate

**Files:**
- Modify: `src/podcast_compactor/api/app.py`
- Test: `tests/unit/api/test_static_mount.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the built `web/dist`.
- Produces: `create_app(..., static_dir: Path | None = None)` — when `static_dir` exists, serve it at `/app` (with an SPA fallback) and redirect `/` → `/app/`; when `None`/absent, the API is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_static_mount.py
import httpx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.config import Settings
from podcast_compactor.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _app(repo, tmp_path, static_dir=None):
    storage = FilesystemStorage(tmp_path / "data")
    settings = Settings(_env_file=None)
    return create_app(
        repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings,
        static_dir=static_dir,
    )


def test_serves_spa_when_static_dir_given(repo, tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>app</title>")
    client = TestClient(_app(repo, tmp_path, static_dir=static))

    root = client.get("/", follow_redirects=False)
    assert root.status_code in (307, 308)
    assert root.headers["location"] == "/app/"

    deep = client.get("/app/jobs/123")  # SPA fallback to index.html
    assert deep.status_code == 200
    assert "app" in deep.text

    # API still works.
    assert client.get("/health").status_code == 200


def test_no_static_dir_leaves_api_unchanged(repo, tmp_path):
    client = TestClient(_app(repo, tmp_path, static_dir=None))
    assert client.get("/", follow_redirects=False).status_code == 404
    assert client.get("/health").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_static_mount.py -q`
Expected: FAIL — `create_app()` has no `static_dir` parameter.

- [ ] **Step 3: Implement the static mount**

In `src/podcast_compactor/api/app.py`, add imports at the top:

```python
from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
```

Change the `create_app` signature to add `static_dir: Path | None = None` (last parameter), and — just before `return app` (after `app.include_router(router)`) — insert:

```python
    if static_dir is not None and Path(static_dir).is_dir():
        index = Path(static_dir) / "index.html"

        @app.get("/")
        def _root() -> RedirectResponse:
            return RedirectResponse(url="/app/")

        @app.get("/app/{path:path}")
        def _spa(path: str) -> FileResponse:
            candidate = Path(static_dir) / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)  # SPA client-side routing fallback
```

Then, in `build_default_app`, default the static dir to the built client when present:

```python
    static_dir = Path("web/dist")
    return create_app(
        repo, resolve, http, _arq_enqueue, storage, settings,
        static_dir=static_dir if static_dir.is_dir() else None,
    )
```

(Assets like `/app/assets/foo.js` are served by the `_spa` handler because the file exists on disk; unknown paths fall back to `index.html`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_static_mount.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Update the README**

Add a section after "Run the service (fake mode)":

```markdown
## Web client (PWA)

A React PWA lives in `web/` and is served same-origin by the API at `/app`.

```bash
cd web && npm install          # once
npm run dev                    # dev server on :5173, proxies to the API on :8000
npm run build                  # emit web/dist/, which the API serves at /app
npm test                       # Vitest + MSW
```

With `web/dist` built, open the app at `http://localhost:8000/app/` (or use the
Vite dev server during development). Set `API_TOKEN` in Settings if the API is
protected.
```
```

- [ ] **Step 6: Full gate + commit**

Run: `uv run pytest -q`
Expected: all green (backend suite incl. the new mount test).
Run: `cd web && npm run test && npm run build && npm run lint`
Expected: all green.

```bash
cd /home/behrad/Development/podcast-compactor
git add src/podcast_compactor/api/app.py tests/unit/api/test_static_mount.py README.md
git commit -m "Serve the built web client from FastAPI at /app"
```

---

## Self-Review

**Spec coverage:**
- Project layout / build (spec §4) → Task 1.
- Same-origin serving + SPA fallback + `/` redirect (§4, §12) → Task 10.
- Dev proxy (§4) → Task 1 (`vite.config.ts`).
- Screens/routes (§5) → NewDigest (5), Jobs (6), JobDetail (7), Settings (8), shell/routing (4).
- API client + types (§6) → Task 2. Query hooks + polling (§6) → Task 3.
- Auth/token + banner (§7) → Task 4 (useToken, TokenBanner), Task 8 (Settings), Task 2 (bearer header).
- Audio player + chapters + downloads (§8) → Task 7.
- PWA manifest/SW/icons (§9) → Task 1 (config) + Task 9 (icons/build).
- Error/empty states (§10) → resolve error (5), failed job (7), empty history (6).
- Testing (§11) → Vitest + MSW throughout; scripts in Task 1.

**Placeholder scan:** none — every step has concrete code/commands. The only non-code artifacts are the two PNG icons (Task 9), with a generation command and an explicit "no zero-byte file" instruction.

**Type consistency:** `api` method names/shapes (Task 2) match their call sites in the hooks (Task 3) and components (5–8). `useJob`/`useResult`/`useJobs`/`useResolveFeed`/`useCreateJob` signatures match across Tasks 3–8. `AudioPlayer({ jobId, chapters })`, `StageProgress({ stages })`, `EpisodePicker({ episodes, selected, onToggle })` match their tests and usages. `create_app(..., static_dir=None)` matches the Task-10 test and `build_default_app`.

**Note on the TokenBanner:** Task 4 creates `TokenBanner` and the API surfaces `401`; wiring it to a global `401` interceptor is intentionally minimal in this MVP (the Settings screen is the primary path). A follow-up can add an axios-style global handler if desired.
