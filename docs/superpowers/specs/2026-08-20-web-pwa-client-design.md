# Web PWA client — design

Date: 2026-08-20
Status: approved (pending spec review)

## 1. Goal

Build the first client for the HTTP API: a **responsive React PWA** that lets a
user resolve a podcast feed, pick episodes, launch a digest job, watch its
progress, and play/download the finished digest — usable on both desktop browsers
and phones from one codebase.

## 2. Non-goals (for now)

- A native mobile app (the PWA covers the mobile surface; native is a later
  project).
- Multi-user accounts / per-user data (the API is single-user).
- Server-side rendering (a static SPA is enough).
- Playwright end-to-end tests (noted as a post-MVP option).
- Offline *use* beyond an app shell — job data always requires the network.

## 3. Decisions (settled during brainstorming)

| Question | Decision |
|---|---|
| Client type | Responsive web app (installable PWA) |
| Stack | React + Vite + TypeScript |
| Serving | FastAPI serves the built SPA same-origin (mounted at `/app`) |
| Data/state | TanStack Query (server state + polling) |
| Routing | React Router (`basename="/app"`) |
| Styling | Tailwind CSS |
| PWA | `vite-plugin-pwa` (manifest + Workbox service worker) |
| Auth | Single-user bearer token from localStorage; optional when API is open |

## 4. Architecture

### Project layout

A new `web/` directory at the repo root, separate from the Python package:

```
web/
  package.json  vite.config.ts  tsconfig.json  index.html
  public/                      # PWA icons, favicon
  src/
    main.tsx  App.tsx
    routes/                    # NewDigest, Jobs, JobDetail, Settings
    api/                       # client.ts (typed fetch), queries.ts (Query hooks), types.ts
    components/                # EpisodePicker, StageProgress, AudioPlayer, TokenBanner, ...
    lib/                       # useToken, formatting helpers
  dist/                        # build output (gitignored)
```

### Same-origin serving

`create_app` gains an **optional** static mount: when a built SPA exists
(`web/dist`, or a configured `static_dir`), FastAPI mounts it at `/app` with
`StaticFiles(html=True)`, adds a catch-all under `/app/{path}` that returns
`index.html` for client-side routes (so refreshing `/app/jobs/123` works), and
redirects `GET /` → `/app/`. API routes stay at root, so there is no collision.
When no build exists (tests, fake-mode dev), nothing is mounted and the API is
unchanged.

### Dev workflow

`vite dev` on `:5173` proxies `/feeds`, `/jobs`, `/health` to FastAPI `:8000`
(configured in `vite.config.ts`), preserving the same-origin illusion with
hot-reload. Production is a single process: `npm run build`, then FastAPI serves
`web/dist` at `/app`.

## 5. Screens & routes

React Router with `basename="/app"`.

1. **`/` — New digest.** Feed URL input → `POST /feeds/resolve` → oldest-first
   episode list (title, date, duration, trailer flag) with checkboxes → options
   (`host_count` 1/2, `target_minutes`, `clone` toggle + guardrail note) →
   **Create** (`POST /jobs`) → navigate to `/jobs/:id`.
2. **`/jobs` — History.** `GET /jobs?limit&offset` → status-badged list
   (created_at, target_minutes), click through to detail. Empty state prompts to
   create one.
3. **`/jobs/:id` — Progress & result.** Polls `GET /jobs/:id`; renders per-stage
   progress (resolve → … → assemble). On `completed`, `GET /jobs/:id/result` →
   summary + chapters + audio player. On `failed`, shows the failing stage and
   `report.skipped`.
4. **`/settings` — Token.** Set/clear the `API_TOKEN` (stored in localStorage).

## 6. Data layer & API client

- **`api/client.ts`** — a thin `fetch` wrapper over relative URLs. Reads the token
  from localStorage and attaches `Authorization: Bearer <token>` when present;
  raises a typed `ApiError` (carrying the status) on non-2xx.
- **`api/types.ts`** — TypeScript mirrors of the API schemas: `EpisodeOut`,
  `ResolveResponse`, `CreateJobRequest`, `JobStatusResponse` (+ `StageOut`),
  `ResultResponse`, `JobListResponse` (+ `JobSummaryOut`).
- **`api/queries.ts`** — TanStack Query hooks:
  - `useResolveFeed()`, `useCreateJob()` — mutations; create invalidates `["jobs"]`.
  - `useJobs(limit, offset)` — the history list.
  - `useJob(id)` — `refetchInterval` ~2 s while `queued`/`running`, stops on
    `completed`/`failed`.
  - `useResult(id)` — `enabled` once the job is `completed`.

## 7. Auth

`useToken()` reads/writes the token in localStorage; the Settings screen edits it.
The client sends the bearer header only when a token is set, so a local
same-origin run with `API_TOKEN` unset needs nothing. A `401` renders a
`TokenBanner` prompting the user to set the token and linking to `/settings`.

## 8. Audio player

`components/AudioPlayer.tsx` wraps a native `<audio>` element with
`src="/jobs/:id/audio?format=mp3"`. The browser issues HTTP Range requests
natively, so scrubbing works with no extra code. Chapters (`result.chapters`)
render as a clickable list — clicking sets `audio.currentTime = start_s`, and the
active chapter is highlighted from `currentTime`. Download links point at
`?format=mp3` and `?format=wav`.

## 9. PWA

`vite-plugin-pwa` with:
- **Manifest:** name/short_name, 192px + 512px icons, `theme_color`,
  `background_color`, `display: standalone`, `start_url: /app/`.
- **Service worker (Workbox `generateSW`):** precache the built app shell for
  offline load, scope `/app/`. API requests use **NetworkOnly** — job status and
  results are dynamic and must never be served stale.

Result: installable on desktop and mobile ("Add to Home Screen") with an app-shell
that opens offline (API actions still require connectivity).

## 10. Error, loading & empty states

- Loading: Query `isLoading` skeletons/spinners on lists and detail.
- Errors: `502` on resolve → "couldn't fetch that feed"; `401` → token banner;
  `409`/not-ready handled by polling rather than surfaced; job `failed` → failing
  stage + `report.skipped` entries.
- Empty: no jobs yet → prompt to create; resolve returns no episodes → message.

## 11. Testing

- **Vitest + React Testing Library**, with **MSW** mocking the API at the network
  layer.
- Coverage: episode-pick + create flow; job-detail polling renders stage states
  and transitions to the result view; result renders chapters and the player; the
  client attaches the bearer header when a token is set and omits it otherwise; a
  `401` surfaces the token banner.
- Scripts: `npm run dev`, `npm run build`, `npm run test`, `npm run lint` (ESLint
  + `tsc --noEmit`).
- Post-MVP: Playwright e2e against a fake-mode backend.

## 12. FastAPI integration (backend touch points)

Small, additive backend changes:
- `create_app` / `build_default_app` gain an optional `static_dir` (default
  `web/dist` if present) and mount the SPA at `/app` as described in §4.
- No change to existing API routes, schemas, or auth.

## 13. Out-of-scope / future

Native mobile app, multi-user accounts, SSE/WebSocket live progress (polling is
enough), server-side rendering, and richer offline support.
