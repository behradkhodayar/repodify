# HTTP API for web & mobile clients — design

Date: 2026-08-20
Status: approved (pending spec review)

## 1. Goal

Extend the existing FastAPI service so that a **web UI** and a **mobile app** can
fully drive the podcast-compactor pipeline: submit jobs, watch progress, and play
or download the finished digest. This effort is **backend only** — the client apps
are separate, later projects. The API is the shared foundation both need.

## 2. Non-goals (for now)

- Building the web UI or the mobile app themselves.
- User accounts / multi-tenant auth. The API is single-user (one shared token).
- Server-Sent Events / WebSocket progress. Clients poll `GET /jobs/{id}`.
- Object storage / CDN delivery (S3). Audio is served from the local filesystem;
  the S3 future is noted where it changes an endpoint.
- `DELETE /jobs/{id}` and other job-management niceties.

## 3. Decisions (settled during brainstorming)

| Question | Decision |
|---|---|
| Scope | Backend API only; clients built separately |
| Auth | Single-user, shared API key (`Authorization: Bearer <token>`) |
| Audio delivery | Serve **both** WAV and a compressed **mp3** (~64 kbps mono) |
| Compression timing | **Eager** transcode in the `assemble` stage (Approach A) |
| Progress | **Polling** the existing `GET /jobs/{id}` |

## 4. Architecture

Keep the existing dependency-injection composition root: `create_app(...)` takes
its collaborators as arguments so tests inject fakes and the worker injects real
ones. Two new arguments are added:

- `storage: Storage` — the API must open files to stream audio bytes.
- `settings: Settings` — supplies the auth token and CORS origins.

New, single-purpose modules (mirroring the existing ports/adapters pattern):

- `api/auth.py` — a `require_token` FastAPI dependency (bearer-token check).
- `api/audio.py` — resolves a job's audio file and returns a Range-capable
  response (see §6).
- `audio/transcode.py` — a `Transcoder` **port** with a real `FfmpegTranscoder`
  (shells out to `ffmpeg`) and a `FakeTranscoder` (writes a stub file) so the
  assemble stage is testable without ffmpeg in CI.
- `JobRepository.list_jobs(limit, offset)` — new repo method for job history.

`ffmpeg` becomes a documented system dependency, alongside the GPU stack.

## 5. Auth & CORS

New settings:

- `api_token: str | None` — when set, every endpoint except `/health` requires
  `Authorization: Bearer <token>`; a missing/incorrect token returns `401` with
  `WWW-Authenticate: Bearer`. When unset, auth is disabled (documented dev-only).
- `cors_allow_origins: list[str]` — wired into `CORSMiddleware`; permissive by
  default for local dev, configurable for real web/mobile origins.

## 6. Endpoints

`⭐` new, `✏️` changed. All except `/health` require the token.

| Method | Path | Purpose |
|---|---|---|
| ⭐ GET | `/health` | Unauthenticated readiness check |
| — | POST `/feeds/resolve` | Resolve feed → episode list (unchanged) |
| — | POST `/jobs` | Create + enqueue job (unchanged) |
| ⭐ GET | `/jobs` | List recent jobs, paginated (`limit`, `offset`) |
| — | GET `/jobs/{id}` | Status + per-stage state (clients poll this) |
| ✏️ GET | `/jobs/{id}/result` | Client-usable audio URLs + summary + chapters |
| ⭐ GET | `/jobs/{id}/audio?format=mp3\|wav` | Range-streamed audio (default `mp3`) |

### Response shapes

- `ResultResponse`: **drop** `output_audio_uri` (a `file://` leak); **add**
  `audio_mp3_url` and `audio_wav_url` (relative paths, e.g.
  `/jobs/{id}/audio?format=mp3`); keep `summary` and `chapters`. Relative URLs so
  clients just prefix their base.
- `JobSummaryOut`: `id, status, created_at, current_stage, target_minutes`.
- `JobListResponse`: `{ jobs: list[JobSummaryOut], total: int }`.

## 7. Audio pipeline & serving

### Transcode (assemble stage)

After the `assemble` node writes `digest.wav`, it calls
`Transcoder.to_mp3(wav) → digest.mp3` and stores it as a second artifact
(`output_audio_mp3`; the WAV stays `output_audio`).

- `FfmpegTranscoder`: `ffmpeg -i digest.wav -c:a libmp3lame -b:a 64k -ac 1
  digest.mp3` (~1–2 s for a 10-min speech digest).
- `FakeTranscoder`: writes a tiny valid stub so pipeline/assemble tests need no
  ffmpeg.

### Range streaming

`GET /jobs/{id}/audio?format=mp3|wav` resolves the file via
`storage.local_path(f"{id}/output/digest.{ext}")` and returns a Starlette
`FileResponse`, which already emits `Accept-Ranges: bytes` and answers `Range:`
requests with `206 Partial Content` — so seeking/scrubbing works with no
hand-rolled byte math. Media types: `audio/mpeg` (mp3), `audio/wav` (wav).

When storage later moves to S3, this endpoint becomes a redirect to a pre-signed
URL — cleanly isolated in `api/audio.py`.

## 8. Error handling

- `401` — missing/incorrect bearer token (when `api_token` is set).
- `404` — unknown `job_id`; requested audio rendition's file is missing.
- `409` — `/result` or `/audio` requested before the job completes (clearer than
  the current `404 "not ready"`).
- `416` — unsatisfiable `Range` (handled by `FileResponse`).
- `422` — malformed request body (FastAPI default).
- `502` — feed-resolve / upstream network failures (instead of a bare `500`).

## 9. Testing

All fakes — no GPU, network, or ffmpeg required.

- **Unit**
  - `require_token`: `401` on wrong/missing token, passes with the correct token,
    disabled when `api_token` is unset.
  - `FakeTranscoder` writes the expected artifact.
  - Audio endpoint via `TestClient`: full `200`, `Range:` → `206` +
    `Content-Range`, bad range → `416`.
  - `JobRepository.list_jobs` ordering + pagination.
- **Integration**
  - Extend the end-to-end pipeline test to assert **both** `digest.wav` and
    `digest.mp3` artifacts exist (via `FakeTranscoder`), `/result` returns the new
    URLs, `/jobs` lists the job, and endpoints reject an absent/incorrect token.

## 10. Out-of-scope future work (tracked separately)

- Web UI and mobile app (their own projects).
- Multi-user accounts (issue-worthy when a second user appears).
- SSE/WebSocket live progress.
- S3-compatible object storage + pre-signed audio URLs (see the deferred-scope
  issue #15).
