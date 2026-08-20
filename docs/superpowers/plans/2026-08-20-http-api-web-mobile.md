# HTTP API for web & mobile clients — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing FastAPI service so a web UI and a mobile app can submit jobs, poll progress, list history, and stream/download the finished digest (both WAV and a compressed mp3), guarded by a single shared API token.

**Architecture:** Keep the existing `create_app(...)` dependency-injection composition root; add `storage` + `settings` arguments. Auth is a bearer-token FastAPI dependency applied to every route except `/health`. Audio is transcoded to mp3 eagerly in the pipeline's `assemble` stage (behind a `Transcoder` port) and served — WAV or mp3 — via Starlette `FileResponse`, which already answers HTTP `Range` requests. Progress uses the existing polling endpoint.

**Tech Stack:** Python 3.12+, FastAPI/Starlette, pydantic-settings, SQLAlchemy, `ffmpeg` (system binary) via `subprocess`, pytest + FastAPI `TestClient` + respx.

## Global Constraints

- Python `>=3.12`; type hints use `X | None` and `from __future__ import annotations`.
- Ruff line-length 100; lint rules `E, F, I, UP, B`. Run `uv run ruff check` before each commit.
- Ports/adapters pattern: the `Protocol` and its `Fake*` live in `ports/`; the real adapter lives in `synth/` or `transcribe/`. Mirror `ports/transcriber.py`.
- Run tests with `uv run pytest`. Tests must pass with no GPU, no network, no ffmpeg (use `FakeTranscoder`); the one real-ffmpeg test is `skipif` guarded.
- Single-user auth: one shared token via `Authorization: Bearer <token>`. No user accounts.
- Compressed audio is mp3, `-b:a 64k -ac 1` (mono).
- Audio URLs returned to clients are **relative** paths (e.g. `/jobs/{id}/audio?format=mp3`).
- Commit messages: imperative mood, what + why, no emojis, no Claude co-authoring, no `feat:`/`fix:` prefixes (match existing repo history).
- Branch: `feat/http-api-web-mobile` (already created off `main`).

---

### Task 1: Transcoder port + FakeTranscoder

**Files:**
- Create: `src/podcast_compactor/ports/transcoder.py`
- Test: `tests/unit/ports/test_transcoder_fake.py`

**Interfaces:**
- Produces: `Transcoder` protocol with `to_mp3(self, src_wav: Path, dst_mp3: Path) -> None`; `FakeTranscoder` (a concrete class implementing it by writing a small stub file).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/ports/test_transcoder_fake.py
from pathlib import Path

from podcast_compactor.ports.transcoder import FakeTranscoder


def test_fake_transcoder_writes_a_nonempty_stub(tmp_path: Path):
    src = tmp_path / "digest.wav"
    src.write_bytes(b"RIFF....WAVE")
    dst = tmp_path / "out" / "digest.mp3"

    FakeTranscoder().to_mp3(src, dst)

    assert dst.exists()
    assert dst.read_bytes()  # non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ports/test_transcoder_fake.py -v`
Expected: FAIL — `ModuleNotFoundError: podcast_compactor.ports.transcoder`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/podcast_compactor/ports/transcoder.py
"""The Transcoder port and a test fake."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Transcoder(Protocol):
    """Transcodes a WAV file to a compressed mp3 rendition."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None: ...


class FakeTranscoder:
    """Writes a tiny stub mp3 so pipeline tests need no ffmpeg."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None:
        dst_mp3.parent.mkdir(parents=True, exist_ok=True)
        dst_mp3.write_bytes(b"ID3fake-mp3")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/ports/test_transcoder_fake.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/ports/transcoder.py tests/unit/ports/test_transcoder_fake.py
git commit -m "Add Transcoder port and fake"
```

---

### Task 2: FfmpegTranscoder (real adapter)

**Files:**
- Create: `src/podcast_compactor/synth/transcode.py`
- Test: `tests/unit/synth/test_transcode.py`

**Interfaces:**
- Consumes: `Transcoder` protocol from Task 1.
- Produces: `FfmpegTranscoder` with `to_mp3(self, src_wav: Path, dst_mp3: Path) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/synth/test_transcode.py
import shutil
import struct
import wave
from pathlib import Path

import pytest

from podcast_compactor.synth.transcode import FfmpegTranscoder


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(struct.pack("<" + "h" * 2400, *([0] * 2400)))  # 0.1s silence


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_transcoder_produces_a_nonempty_mp3(tmp_path: Path):
    src = tmp_path / "digest.wav"
    _tiny_wav(src)
    dst = tmp_path / "out" / "digest.mp3"

    FfmpegTranscoder().to_mp3(src, dst)

    assert dst.exists()
    assert dst.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/synth/test_transcode.py -v`
Expected: FAIL — `ModuleNotFoundError: podcast_compactor.synth.transcode`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/podcast_compactor/synth/transcode.py
"""ffmpeg-backed Transcoder (real adapter; requires the `ffmpeg` binary)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class FfmpegTranscoder:
    """Transcodes WAV to a small mono mp3 via the system ffmpeg binary."""

    def to_mp3(self, src_wav: Path, dst_mp3: Path) -> None:
        dst_mp3.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src_wav),
                "-c:a", "libmp3lame", "-b:a", "64k", "-ac", "1",
                str(dst_mp3),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg transcode failed ({result.returncode}): "
                f"{result.stderr.decode(errors='replace')[-500:]}"
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/synth/test_transcode.py -v`
Expected: PASS (a real mp3 is produced).

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/synth/transcode.py tests/unit/synth/test_transcode.py
git commit -m "Add ffmpeg Transcoder adapter"
```

---

### Task 3: Produce mp3 in the assemble stage

**Files:**
- Modify: `src/podcast_compactor/pipeline/state.py` (add `transcoder` to `Deps`)
- Modify: `src/podcast_compactor/pipeline/nodes.py:214-243` (assemble section)
- Modify: `src/podcast_compactor/worker/main.py` (wire transcoder in `build_deps`)
- Modify: `tests/integration/test_pipeline_end_to_end.py` (pass `transcoder`, assert mp3)
- Modify: `tests/integration/test_pipeline_releases_gpu.py` (pass `transcoder`)

**Interfaces:**
- Consumes: `Transcoder`/`FakeTranscoder` (Task 1), `FfmpegTranscoder` (Task 2).
- Produces: a `digest.mp3` object under `{job_id}/output/` and an `output_audio_mp3` artifact whenever a job completes.

- [ ] **Step 1: Write the failing test** — extend the end-to-end test's assertions (add near the artifact checks around line 111-115) and pass a transcoder into `Deps`.

In `tests/integration/test_pipeline_end_to_end.py`, add the import:

```python
from podcast_compactor.ports.transcoder import FakeTranscoder
```

Add `transcoder=FakeTranscoder(),` to the `Deps(...)` construction (alongside the other deps), then add these assertions after the existing `kinds` block:

```python
    assert "output_audio_mp3" in kinds
    assert storage.get_bytes(f"{job_id}/output/digest.mp3")  # non-empty mp3 written
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pipeline_end_to_end.py -v`
Expected: FAIL — `TypeError: Deps.__init__() missing ... 'transcoder'` (after adding the arg, then) `assert "output_audio_mp3" in kinds` fails because the node doesn't write it yet.

- [ ] **Step 3: Add the `transcoder` field to `Deps`**

In `src/podcast_compactor/pipeline/state.py`, add the import and the field. Place `transcoder` **before** `intro_outro` (a dataclass can't have a non-default field after a default one):

```python
from podcast_compactor.ports.transcoder import Transcoder
```

```python
    repo: JobRepository
    settings: Settings
    transcoder: Transcoder
    intro_outro: dict[str, bytes] = field(default_factory=dict)
```

- [ ] **Step 4: Call the transcoder in the assemble node**

In `src/podcast_compactor/pipeline/nodes.py`, in `synth_node`'s ASSEMBLE block, immediately after
`output_uri = deps.storage.put_bytes(f"{job_id}/output/digest.wav", wav)` (line 220), insert:

```python
            mp3_path = deps.storage.local_path(f"{job_id}/output/digest.mp3")
            deps.transcoder.to_mp3(
                deps.storage.local_path(f"{job_id}/output/digest.wav"), mp3_path
            )
```

And after `repo.add_artifact(job_id, "output_audio", output_uri)` (line 234), insert:

```python
            repo.add_artifact(job_id, "output_audio_mp3", mp3_path.as_uri())
```

- [ ] **Step 5: Wire the transcoder in `build_deps`**

In `src/podcast_compactor/worker/main.py`: in the `use_fakes` branch add
`from podcast_compactor.ports.transcoder import FakeTranscoder` and `transcoder = FakeTranscoder()`;
in the real branch add `from podcast_compactor.synth.transcode import FfmpegTranscoder` and
`transcoder = FfmpegTranscoder()`. Then add `transcoder=transcoder,` to the `return Deps(...)` call.

- [ ] **Step 6: Fix the other integration Deps construction**

In `tests/integration/test_pipeline_releases_gpu.py`, add `from podcast_compactor.ports.transcoder import FakeTranscoder` and `transcoder=FakeTranscoder(),` to its `Deps(...)` construction.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/integration -v`
Expected: PASS (both integration tests green; mp3 artifact asserted).

- [ ] **Step 8: Commit**

```bash
git add src/podcast_compactor/pipeline/state.py src/podcast_compactor/pipeline/nodes.py \
        src/podcast_compactor/worker/main.py tests/integration/test_pipeline_end_to_end.py \
        tests/integration/test_pipeline_releases_gpu.py
git commit -m "Transcode the digest to mp3 in the assemble stage"
```

---

### Task 4: API settings (token + CORS origins)

**Files:**
- Modify: `src/podcast_compactor/config.py`
- Test: `tests/unit/test_config_api_settings.py`

**Interfaces:**
- Produces: `Settings.api_token: str | None` (default `None`) and `Settings.cors_allow_origins: list[str]` (default `["*"]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config_api_settings.py
from podcast_compactor.config import Settings


def test_api_settings_defaults():
    s = Settings(_env_file=None)
    assert s.api_token is None
    assert s.cors_allow_origins == ["*"]


def test_api_token_override():
    s = Settings(_env_file=None, api_token="secret")
    assert s.api_token == "secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config_api_settings.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'api_token'`.

- [ ] **Step 3: Write minimal implementation**

In `src/podcast_compactor/config.py`, add after the `hf_token` field:

```python
    # HTTP API
    api_token: str | None = None  # when set, all endpoints except /health require it
    cors_allow_origins: list[str] = ["*"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config_api_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/config.py tests/unit/test_config_api_settings.py
git commit -m "Add api_token and cors_allow_origins settings"
```

---

### Task 5: Bearer-token auth dependency

**Files:**
- Create: `src/podcast_compactor/api/auth.py`
- Test: `tests/unit/api/test_auth.py`

**Interfaces:**
- Produces: `make_require_token(expected: str | None) -> Callable` — a FastAPI dependency that raises `401` on a missing/incorrect `Authorization: Bearer` header, and is a no-op when `expected is None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_auth.py
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from podcast_compactor.api.auth import make_require_token


def _client(token):
    app = FastAPI()

    @app.get("/x", dependencies=[Depends(make_require_token(token))])
    def x():
        return {"ok": True}

    return TestClient(app)


def test_rejects_missing_token():
    assert _client("secret").get("/x").status_code == 401


def test_rejects_wrong_token():
    r = _client("secret").get("/x", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_accepts_correct_token():
    r = _client("secret").get("/x", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200


def test_disabled_when_token_is_none():
    assert _client(None).get("/x").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: podcast_compactor.api.auth`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/podcast_compactor/api/auth.py
"""Bearer-token auth dependency for the single-user API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException, status


def make_require_token(expected: str | None) -> Callable[[str | None], None]:
    """Build a dependency that enforces `Authorization: Bearer <expected>`.

    A no-op when `expected` is None (auth disabled, dev-only).
    """

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if expected is None:
            return
        if authorization != f"Bearer {expected}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return require_token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/api/auth.py tests/unit/api/test_auth.py
git commit -m "Add bearer-token auth dependency"
```

---

### Task 6: `JobRepository.list_jobs`

**Files:**
- Modify: `src/podcast_compactor/persistence/repo.py`
- Test: `tests/unit/persistence/test_repo_list_jobs.py`

**Interfaces:**
- Produces: `JobRepository.list_jobs(self, limit: int = 50, offset: int = 0) -> tuple[list[Job], int]` — newest-first jobs plus the total count.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/persistence/test_repo_list_jobs.py
from podcast_compactor.models.domain import JobOptions


def test_list_jobs_newest_first_with_total(repo):
    ids = [repo.create_job(f"https://feed/{i}", JobOptions(episode_ids=["e"])) for i in range(3)]

    jobs, total = repo.list_jobs(limit=2, offset=0)

    assert total == 3
    assert [j.id for j in jobs] == [ids[2], ids[1]]  # newest first, limited to 2


def test_list_jobs_offset(repo):
    ids = [repo.create_job(f"https://feed/{i}", JobOptions(episode_ids=["e"])) for i in range(3)]

    jobs, total = repo.list_jobs(limit=2, offset=2)

    assert total == 3
    assert [j.id for j in jobs] == [ids[0]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/persistence/test_repo_list_jobs.py -v`
Expected: FAIL — `AttributeError: 'JobRepository' object has no attribute 'list_jobs'`.

Note: `Job.created_at` defaults to `datetime.now(UTC)`; the three jobs are created in order so newest-first ordering is deterministic by insertion. If timestamps tie at the same microsecond, this test may be flaky — if so, order by `created_at.desc(), id.desc()` in Step 3 (already included below).

- [ ] **Step 3: Write minimal implementation**

In `src/podcast_compactor/persistence/repo.py`, change the import line
`from sqlalchemy import select` to `from sqlalchemy import func, select`, then add this method:

```python
    def list_jobs(self, limit: int = 50, offset: int = 0) -> tuple[list[Job], int]:
        with self._sf() as s:
            total = s.scalar(select(func.count()).select_from(Job)) or 0
            rows = list(
                s.scalars(
                    select(Job)
                    .order_by(Job.created_at.desc(), Job.id.desc())
                    .limit(limit)
                    .offset(offset)
                ).all()
            )
            for job in rows:
                _ = list(job.stages), list(job.artifacts)
            s.expunge_all()
            return rows, total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/persistence/test_repo_list_jobs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/persistence/repo.py tests/unit/persistence/test_repo_list_jobs.py
git commit -m "Add JobRepository.list_jobs with total count"
```

---

### Task 7: Rewire `create_app` — storage/settings args, auth, CORS, /health, resolve 502

**Files:**
- Modify: `src/podcast_compactor/api/app.py`
- Modify: `tests/unit/api/test_api.py` (update `create_app` calls; add /health + auth tests)

**Interfaces:**
- Consumes: `make_require_token` (Task 5); `Storage`, `Settings`.
- Produces: `create_app(repo, resolve_fn, http, enqueue, storage, settings) -> FastAPI` with a `GET /health` (unauthenticated) route, CORS middleware, all other routes behind the token, and `POST /feeds/resolve` mapping upstream `httpx.HTTPError` to `502`.

- [ ] **Step 1: Write the failing test** — add to `tests/unit/api/test_api.py`. First add imports and a helper at the top:

```python
from fastapi import FastAPI
from podcast_compactor.config import Settings
from podcast_compactor.storage.filesystem import FilesystemStorage


def _app(repo, http, tmp_path, enqueue=lambda jid: None, token=None):
    storage = FilesystemStorage(tmp_path / "data")
    settings = Settings(_env_file=None, api_token=token)
    return create_app(repo, _resolve_fn, http, enqueue, storage, settings)
```

Then add new tests:

```python
def test_health_is_unauthenticated(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path, token="secret"))
        assert client.get("/health").status_code == 200


def test_protected_route_requires_token(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path, token="secret"))
        assert client.get("/jobs/does-not-exist").status_code == 401
        ok = client.get("/jobs/does-not-exist", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_api.py -v`
Expected: FAIL — `create_app()` got unexpected/again missing args, and `/health` 404.

- [ ] **Step 3: Rewrite `create_app` and `build_default_app`**

Replace `src/podcast_compactor/api/app.py` with:

```python
"""FastAPI application factory.

`create_app` takes its collaborators as arguments so tests can inject fakes and
the worker/composition root can inject real ones.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from podcast_compactor.api.audio import audio_response
from podcast_compactor.api.auth import make_require_token
from podcast_compactor.api.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    EpisodeOut,
    JobListResponse,
    JobStatusResponse,
    JobSummaryOut,
    ResolveRequest,
    ResolveResponse,
    ResultResponse,
    StageOut,
)
from podcast_compactor.config import Settings, get_settings
from podcast_compactor.ingest.feed import parse_feed
from podcast_compactor.ingest.resolvers import resolve
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository
from podcast_compactor.storage.base import Storage
from podcast_compactor.storage.filesystem import FilesystemStorage

ResolveFn = Callable[[str, httpx.Client], str]
EnqueueFn = Callable[[str], None]


def create_app(
    repo: JobRepository,
    resolve_fn: ResolveFn,
    http: httpx.Client,
    enqueue: EnqueueFn,
    storage: Storage,
    settings: Settings,
) -> FastAPI:
    app = FastAPI(title="Podcast Compactor")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    router = APIRouter(dependencies=[Depends(make_require_token(settings.api_token))])

    @router.post("/feeds/resolve", response_model=ResolveResponse)
    def resolve_feed(req: ResolveRequest) -> ResolveResponse:
        try:
            rss_url = resolve_fn(req.url, http)
            resp = http.get(rss_url, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"feed fetch failed: {exc}") from exc
        feed = parse_feed(req.url, rss_url, resp.content)
        return ResolveResponse(
            feed_title=feed.title,
            rss_url=feed.rss_url,
            episodes=[EpisodeOut(**e.model_dump()) for e in feed.episodes],
        )

    @router.post("/jobs", response_model=CreateJobResponse)
    def create_job(req: CreateJobRequest) -> CreateJobResponse:
        options = JobOptions(
            episode_ids=req.episode_ids,
            host_count=req.host_count,
            clone=req.clone,
            target_minutes=req.target_minutes,
        )
        job_id = repo.create_job(req.feed_url, options)
        enqueue(job_id)
        return CreateJobResponse(job_id=job_id)

    @router.get("/jobs", response_model=JobListResponse)
    def list_jobs(limit: int = 50, offset: int = 0) -> JobListResponse:
        jobs, total = repo.list_jobs(limit=limit, offset=offset)
        return JobListResponse(
            jobs=[
                JobSummaryOut(
                    id=j.id,
                    status=j.status,
                    current_stage=j.current_stage,
                    target_minutes=JobOptions.model_validate_json(j.options_json).target_minutes,
                    created_at=j.created_at,
                )
                for j in jobs
            ],
            total=total,
        )

    @router.get("/jobs/{job_id}", response_model=JobStatusResponse)
    def get_status(job_id: str) -> JobStatusResponse:
        try:
            job = repo.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JobStatusResponse(
            id=job.id,
            status=job.status,
            current_stage=job.current_stage,
            stages=[
                StageOut(
                    stage=s.stage,
                    state=s.state,
                    detail=s.detail,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in job.stages
            ],
            report=json.loads(job.report_json or "{}"),
        )

    @router.get("/jobs/{job_id}/result", response_model=ResultResponse)
    def get_result(job_id: str) -> ResultResponse:
        job = _require_completed(repo, job_id)
        report = json.loads(job.report_json or "{}")
        show_notes = report.get("show_notes") or {}
        return ResultResponse(
            audio_mp3_url=f"/jobs/{job_id}/audio?format=mp3",
            audio_wav_url=f"/jobs/{job_id}/audio?format=wav",
            summary=show_notes.get("summary", ""),
            chapters=show_notes.get("chapters", []),
        )

    @router.get("/jobs/{job_id}/audio")
    def get_audio(job_id: str, format: str = "mp3"):
        _require_completed(repo, job_id)
        return audio_response(storage, job_id, format)

    app.include_router(router)
    return app


def _require_completed(repo: JobRepository, job_id: str):
    try:
        job = repo.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="job not complete")
    return job


def _arq_enqueue(job_id: str) -> None:
    """Enqueue a job onto arq/Redis. Opens a short-lived pool per call."""
    import asyncio

    from arq import create_pool
    from arq.connections import RedisSettings

    async def _go() -> None:
        pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            await pool.enqueue_job("run_job", job_id)
        finally:
            await pool.aclose()

    asyncio.run(_go())


def build_default_app() -> FastAPI:
    """Composition root for the API. Use with `uvicorn ... --factory`."""
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    repo = JobRepository(session_factory(engine))
    http = httpx.Client(timeout=60.0)
    storage = FilesystemStorage(settings.data_dir)
    return create_app(repo, resolve, http, _arq_enqueue, storage, settings)
```

Note: this references `audio_response` (Task 9), `JobListResponse`/`JobSummaryOut`/the new `ResultResponse` (Tasks 8 & 10). Those are created in later tasks — if executing strictly in order, this task's imports will not resolve until Tasks 8–10 land. Execute Tasks 8, 9, 10's **schema/module creation steps** together with this task if running inline, or accept that the app module is import-incomplete until Task 10's final gate. The existing three tests below only exercise routes that already work.

- [ ] **Step 4: Update the three existing `create_app` calls**

In `tests/unit/api/test_api.py`, change each `create_app(repo, _resolve_fn, http, enqueue=...)` to use the `_app(...)` helper, e.g.:
- `test_resolve_lists_episodes_oldest_first`: `client = TestClient(_app(repo, http, tmp_path))` (add `tmp_path` param to the test).
- `test_create_job_enqueues_and_status_reports_queued`: `TestClient(_app(repo, http, tmp_path, enqueue=enqueued.append))` (add `tmp_path`). **Leave the `/result` == 404 assertion for now** — it becomes 409 in Task 10.
- `test_result_returned_when_completed`: `TestClient(_app(repo, http, tmp_path))` (add `tmp_path`). **Leave its body assertions for now** — updated in Task 10.

- [ ] **Step 5: Run tests (auth + health only, since app import needs Tasks 8-10)**

If executing inline, defer running the full `test_api.py` until Task 10. Otherwise run just the new tests once Tasks 8-10 are in:
Run: `uv run pytest tests/unit/api/test_api.py::test_health_is_unauthenticated tests/unit/api/test_api.py::test_protected_route_requires_token -v`
Expected: PASS.

- [ ] **Step 6: Commit** (commit together with Tasks 8-10 if running inline to keep the module importable)

```bash
git add src/podcast_compactor/api/app.py tests/unit/api/test_api.py
git commit -m "Add auth, CORS, health, and job-list wiring to the API"
```

---

### Task 8: Job-list & result schemas

**Files:**
- Modify: `src/podcast_compactor/api/schemas.py`

**Interfaces:**
- Produces: `JobSummaryOut`, `JobListResponse`, and the revised `ResultResponse` (fields `audio_mp3_url`, `audio_wav_url`, `summary`, `chapters`).

- [ ] **Step 1: Add the schemas** (exercised by Tasks 7/9/10 endpoint tests — no standalone test).

In `src/podcast_compactor/api/schemas.py`, replace the `ResultResponse` class and append the two list schemas:

```python
class ResultResponse(BaseModel):
    audio_mp3_url: str
    audio_wav_url: str
    summary: str
    chapters: list[ChapterOut]


class JobSummaryOut(BaseModel):
    id: str
    status: str
    current_stage: str | None = None
    target_minutes: int
    created_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobSummaryOut]
    total: int
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from podcast_compactor.api import schemas; print(schemas.JobListResponse, schemas.ResultResponse)"`
Expected: prints both classes, no error.

- [ ] **Step 3: Commit** (with Task 7 if inline)

```bash
git add src/podcast_compactor/api/schemas.py
git commit -m "Add job-list schemas and client audio URLs to result"
```

---

### Task 9: Audio streaming endpoint

**Files:**
- Create: `src/podcast_compactor/api/audio.py`
- Test: `tests/unit/api/test_audio.py`

**Interfaces:**
- Consumes: `Storage`; the `create_app` `get_audio` route (Task 7).
- Produces: `audio_response(storage: Storage, job_id: str, fmt: str) -> FileResponse` — `422` for a bad format, `404` when the rendition file is absent, otherwise a `FileResponse` that supports `Range`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_audio.py
import httpx
from fastapi.testclient import TestClient

from podcast_compactor.api.app import create_app
from podcast_compactor.config import Settings
from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus
from podcast_compactor.storage.filesystem import FilesystemStorage


def _resolve_fn(url, http):
    return "https://feed.example.com/feed.xml"


def _completed_job_with_audio(repo, storage):
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    storage.put_bytes(f"{job_id}/output/digest.wav", b"RIFF-fake-wav-bytes")
    storage.put_bytes(f"{job_id}/output/digest.mp3", b"ID3-fake-mp3-bytes!!")
    repo.set_status(job_id, JobStatus.COMPLETED)
    return job_id


def _client(repo, storage):
    settings = Settings(_env_file=None)
    return TestClient(create_app(repo, _resolve_fn, httpx.Client(), lambda j: None, storage, settings))


def test_audio_full_download(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    r = _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers.get("accept-ranges") == "bytes"
    assert r.content == b"ID3-fake-mp3-bytes!!"


def test_audio_range_request_returns_206(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    r = _client(repo, storage).get(
        f"/jobs/{job_id}/audio?format=mp3", headers={"Range": "bytes=0-3"}
    )
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-3/")
    assert r.content == b"ID3-"


def test_audio_bad_format_is_422(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = _completed_job_with_audio(repo, storage)
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=flac").status_code == 422


def test_audio_missing_file_is_404(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))
    repo.set_status(job_id, JobStatus.COMPLETED)  # completed but no files written
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3").status_code == 404


def test_audio_not_complete_is_409(repo, tmp_path):
    storage = FilesystemStorage(tmp_path / "data")
    job_id = repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"]))  # queued
    assert _client(repo, storage).get(f"/jobs/{job_id}/audio?format=mp3").status_code == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_audio.py -v`
Expected: FAIL — `ModuleNotFoundError: podcast_compactor.api.audio` (and thus `create_app` import fails).

- [ ] **Step 3: Write minimal implementation**

```python
# src/podcast_compactor/api/audio.py
"""Serve a job's rendered audio, with HTTP Range support via FileResponse."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import FileResponse

from podcast_compactor.storage.base import Storage

_MEDIA_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}


def audio_response(storage: Storage, job_id: str, fmt: str) -> FileResponse:
    media_type = _MEDIA_TYPES.get(fmt)
    if media_type is None:
        raise HTTPException(status_code=422, detail="format must be 'mp3' or 'wav'")
    key = f"{job_id}/output/digest.{fmt}"
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(
        storage.local_path(key), media_type=media_type, filename=f"digest.{fmt}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/api/test_audio.py -v`
Expected: PASS (Starlette `FileResponse` emits `Accept-Ranges` and answers `Range` with `206`).

If `test_audio_range_request_returns_206` fails because the installed Starlette does not range-handle `FileResponse`, fall back to a small explicit Range handler in `audio.py` (read `Range` header, return `206` with `Content-Range` and the byte slice, `416` on an unsatisfiable range). Keep the same `audio_response` signature.

- [ ] **Step 5: Commit**

```bash
git add src/podcast_compactor/api/audio.py tests/unit/api/test_audio.py
git commit -m "Serve job audio with HTTP range support"
```

---

### Task 10: Result URLs + not-ready 409, and final gate

**Files:**
- Modify: `tests/unit/api/test_api.py` (result assertions + queued→409, add `/jobs` list test)

**Interfaces:**
- Consumes: everything above. No new production code — `create_app` already returns the new `ResultResponse` and `409` (Task 7).

- [ ] **Step 1: Update the result + queued tests and add a list test**

In `tests/unit/api/test_api.py`:

Change the queued-job assertion in `test_create_job_enqueues_and_status_reports_queued` from
`assert client.get(f"/jobs/{job_id}/result").status_code == 404` to `== 409`.

Replace the body of `test_result_returned_when_completed`'s assertions with:

```python
    assert resp.status_code == 200
    body = resp.json()
    assert body["audio_mp3_url"] == f"/jobs/{job_id}/audio?format=mp3"
    assert body["audio_wav_url"] == f"/jobs/{job_id}/audio?format=wav"
    assert body["summary"] == "the story"
    assert body["chapters"][0]["title"] == "Intro"
```

(The `repo.add_artifact(job_id, "output_audio", ...)` line in that test is now unused by `/result` but harmless — leave it.)

Add a list test:

```python
def test_jobs_list_returns_created_jobs(repo, tmp_path):
    repo.create_job("https://feed", JobOptions(episode_ids=["ep-1"], target_minutes=10))
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        body = client.get("/jobs").json()
    assert body["total"] == 1
    assert body["jobs"][0]["target_minutes"] == 10
```

- [ ] **Step 2: Run the full API test module**

Run: `uv run pytest tests/unit/api -v`
Expected: PASS (auth, audio, resolve, create/status, result, list).

- [ ] **Step 3: Full suite + lint gate**

Run: `uv run pytest`
Expected: all green.
Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/unit/api/test_api.py
git commit -m "Return client audio URLs and 409-not-ready from the API"
```

---

## Self-Review

**Spec coverage:**
- Auth (§5) → Tasks 4, 5, 7. CORS (§5) → Task 7. `/health` → Task 7.
- Endpoint table (§6): `/jobs` list → Tasks 6, 8, 7; changed `/result` → Tasks 8, 10; `/jobs/{id}/audio` → Task 9; existing routes preserved → Task 7.
- Response shapes (§6): `ResultResponse`, `JobSummaryOut`, `JobListResponse` → Task 8; relative URLs → Task 10.
- Transcode in assemble (§7) → Tasks 1, 2, 3. Range streaming (§7) → Task 9.
- Error map (§8): `401` → Task 5/7; `404` → Tasks 7/9; `409` → Tasks 7/10; `416`/`422` → Task 9; `502` → Task 7.
- Testing (§9): unit (auth, fake transcoder, audio range, list_jobs) and integration (mp3 artifact, result URLs, auth) all covered.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `to_mp3(src_wav, dst_mp3)` identical across Tasks 1/2/3. `audio_response(storage, job_id, fmt)` matches its Task-7 call site. `list_jobs(limit, offset) -> tuple[list[Job], int]` matches the Task-7 usage. `make_require_token(expected)` matches Tasks 5/7. `ResultResponse` fields match between Tasks 8 and 10.

**Ordering caveat (called out in Task 7):** the new `app.py` imports `audio_response` and the new schemas, so Tasks 7–10 must all land before `podcast_compactor.api.app` imports cleanly. Under subagent-driven execution, run Tasks 1–6 with green gates, then treat 7–10 as one reviewable batch whose gate is the Task 10 full-suite run.
