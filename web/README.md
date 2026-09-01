# Repodify web client

The React 19 + Vite PWA for [Repodify](../README.md). It's served same-origin by
the API at `/app` (client-side router `basename="/app"`, Vite `base: '/app/'`) and
drives the whole flow: search a show, pick episodes, configure the digest, step
through the pipeline gates, and stream the finished audio.

Most of the time you don't run this directly — [`./launch`](../launch) builds and
serves it for you. Use the commands below when working on the client itself.

## Commands

```bash
npm install        # once
npm run dev        # dev server on :5173, proxies API calls to :8000
npm run build      # tsc -b && vite build → web/dist/, which the API serves at /app
npm run preview    # preview the production build
npm test           # Vitest + MSW component/hook tests
npm run lint       # tsc -b (type check)
```

The dev server proxies `/feeds`, `/jobs`, `/voices`, `/settings`, and `/health` to
`API_PROXY_TARGET` (default `http://localhost:8000`). If the API is protected by
`API_TOKEN`, set the token on the **Settings** screen — the client stores it in
`localStorage.api_token` and sends it as a bearer token.

## Stack & layout

- **React 19**, **Vite 8**, **Tailwind**, **TanStack Query**, **React Router 7**,
  **Radix UI** primitives, **Framer Motion**.
- `src/api/` — `client.ts` (same-origin fetch + bearer), `queries.ts` (query hooks),
  `types.ts` (mirrors `api/schemas.py` — keep them aligned).
- `src/routes/` — Overview, NewDigest, Jobs (history), JobDetail, Settings.
- `src/components/` — feature components + `ui/` primitives + `layout/` shell.
- `src/lib/` — theme, formatting, nav, hooks.
- Tests are co-located as `*.test.ts(x)`; MSW handlers live in `src/test/msw.ts`
  and are configured `onUnhandledRequest: 'error'`.

## Conventions

- Keep `src/api/types.ts` in sync with the backend schemas in
  `src/repodify/api/schemas.py`.
- Don't duplicate pipeline business rules in the client — it renders gates and
  progress; the backend owns the logic.
- After UI changes, run `npm test` and check both desktop and mobile viewports.
