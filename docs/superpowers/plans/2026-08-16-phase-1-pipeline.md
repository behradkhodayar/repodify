# Phase 1 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 vertical slice of Repodify: a backend service that takes a podcast link, lets a user select episodes, and produces a single ~30-minute single-narrator digest audio file plus show notes — end to end.

**Architecture:** A LangGraph `StateGraph` drives an 8-stage pipeline (resolve → list → download → transcribe → summarize → arc → script → tts+assemble). Each ML-heavy stage sits behind a small port (Protocol) with a real implementation and a test fake, so the whole pipeline runs on CPU in tests while the real faster-whisper / F5-TTS implementations are used on a GPU host. A FastAPI app enqueues jobs onto arq/Redis; a worker runs the graph and records per-stage progress in SQLite/Postgres.

**Tech Stack:** Python 3.12, FastAPI, arq (Redis), SQLAlchemy 2.x (SQLite dev / Postgres prod), LangGraph, langchain-anthropic, feedparser, httpx, faster-whisper (GPU extra), F5-TTS (GPU extra), pydantic v2, pydantic-settings, pytest.

## Global Constraints

- Python 3.12+.
- English-only content (Phase 1).
- Heavy ML deps (`torch`, `faster-whisper`, `f5-tts`, `pyannote.audio`) live in an optional `[gpu]` extra and are **imported lazily** inside their real implementation modules — core install and the test suite MUST NOT require them.
- Every stage that touches an LLM, STT, or TTS is accessed through a Protocol port; tests use fakes. No network or GPU in the default test run.
- Structured LLM output goes through the `StructuredLLM` port (§ Task 8), never raw string parsing.
- Word budget for script length: `words = target_minutes * wpm`, default `wpm = 130`.
- TDD: failing test first, minimal impl, commit per task. Commit messages imperative, no emojis, no Claude co-authorship.
- Audio in tests uses stdlib `wave` (WAV); MP3 export (needs ffmpeg) is a separate, non-test-gated path.

---

## File Structure

```
pyproject.toml                       # project + deps + [gpu] extra + pytest/ruff config
.env.example                         # documented settings
README.md                            # run instructions
docker-compose.yml                   # postgres + redis for local prod-like run
src/repodify/
  __init__.py
  config.py                          # pydantic-settings Settings
  models/
    domain.py                        # pydantic domain models (Feed, Episode, Transcript, ...)
    enums.py                         # StageName, JobStatus, StageState
    db.py                            # SQLAlchemy ORM: Job, EpisodeRow, StageStatus, Artifact
  storage/
    base.py                          # Storage Protocol
    filesystem.py                    # FilesystemStorage
  ports/
    llm.py                           # StructuredLLM Protocol + AnthropicStructuredLLM + FakeStructuredLLM
    transcriber.py                   # Transcriber Protocol + FakeTranscriber
    tts.py                           # TTS Protocol + Voice + FakeTTS
  ingest/
    resolvers.py                     # Resolver Protocol + Raw/Apple/Castbox resolvers + resolve()
    feed.py                          # parse_feed(bytes) -> Feed
    download.py                      # download_episode(...)
  transcribe/
    faster_whisper.py                # FasterWhisperTranscriber (lazy import)
  summarize/
    prompts.py                       # prompt strings
    chains.py                        # summarize_episode(), synthesize_arc()
  script/
    writer.py                        # write_script()
  synth/
    f5_tts.py                        # F5TTS (lazy import)
    assemble.py                      # synthesize_script(), assemble_wav(), build_show_notes()
  persistence/
    repo.py                          # JobRepository (create/get/update stage/attach artifact)
    engine.py                        # engine/session factory
  pipeline/
    state.py                         # PipelineState TypedDict + Deps dataclass
    nodes.py                         # node functions (closures over Deps)
    graph.py                         # build_graph(deps) -> compiled StateGraph
  api/
    schemas.py                       # request/response models
    routers.py                       # endpoints
    app.py                           # FastAPI app factory
  worker/
    main.py                          # arq WorkerSettings + run_job task
tests/
  conftest.py                        # fixtures: tmp storage, fakes, sample RSS
  fixtures/sample_feed.xml
  unit/... (mirrors src)
  integration/test_pipeline_end_to_end.py
```

**Dependency direction:** `models`, `storage`, `ports` are leaves. `ingest/transcribe/summarize/script/synth` depend on those. `persistence` depends on `models`. `pipeline` wires everything via `Deps`. `api`/`worker` are the outermost shells.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.env.example`, `README.md`, `src/repodify/__init__.py`, `src/repodify/config.py`, `tests/conftest.py`, `tests/unit/test_config.py`

**Interfaces:**
- Produces: `repodify.config.Settings` (pydantic-settings) with fields `anthropic_api_key: str | None`, `database_url: str = "sqlite:///./data/app.db"`, `redis_url: str`, `data_dir: Path = Path("data")`, `use_fakes: bool = True`, `whisper_model: str = "large-v3"`, `wpm: int = 130`, `map_model: str = "claude-haiku-4-5-20251001"`, `reduce_model: str = "claude-opus-4-8"`; `get_settings()` cached accessor.

- [ ] **Step 1: Write failing test** — `tests/unit/test_config.py`

```python
from repodify.config import Settings

def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("USE_FAKES", raising=False)
    s = Settings(_env_file=None)
    assert s.wpm == 130
    assert s.use_fakes is True
    assert str(s.database_url).startswith("sqlite")
```

- [ ] **Step 2: Run — expect ImportError/FAIL**: `pytest tests/unit/test_config.py -v`
- [ ] **Step 3: Write `pyproject.toml`** — core deps + `[project.optional-dependencies] gpu = ["torch", "faster-whisper", "f5-tts", "pyannote.audio"]`, `[tool.pytest.ini_options] pythonpath=["src"] testpaths=["tests"]`, ruff config. Core deps: `fastapi`, `uvicorn`, `arq`, `sqlalchemy`, `langgraph`, `langchain-anthropic`, `langchain-core`, `feedparser`, `httpx`, `pydantic`, `pydantic-settings`.
- [ ] **Step 4: Write `config.py`** — `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")` and fields above; `@lru_cache get_settings()`.
- [ ] **Step 5: Write `.env.example`** documenting each var; `README.md` with venv + install + test instructions.
- [ ] **Step 6: Create venv, install**: `python -m venv .venv && .venv/bin/pip install -e ".[dev]"` (dev extra = pytest, ruff, respx).
- [ ] **Step 7: Run — expect PASS**: `.venv/bin/pytest tests/unit/test_config.py -v`
- [ ] **Step 8: Commit**: `git add -A && git commit -m "Add project scaffold and settings"`

---

## Task 2: Domain models & enums

**Files:**
- Create: `src/repodify/models/enums.py`, `src/repodify/models/domain.py`, `tests/unit/models/test_domain.py`

**Interfaces:**
- Produces (enums): `StageName{RESOLVE,LIST,DOWNLOAD,TRANSCRIBE,SUMMARIZE,ARC,SCRIPT,TTS,ASSEMBLE}`, `JobStatus{QUEUED,RUNNING,COMPLETED,FAILED}`, `StageState{PENDING,RUNNING,DONE,SKIPPED,FAILED}` (all `str, Enum`).
- Produces (domain, pydantic `BaseModel`):
  - `Episode{guid:str, title:str, published_at:datetime|None, duration_s:int|None, audio_url:str, order_index:int, is_short_or_trailer:bool=False}`
  - `Feed{source_url:str, rss_url:str, title:str, author:str|None=None, episodes:list[Episode]}`
  - `TranscriptSegment{start:float, end:float, text:str}`
  - `Transcript{episode_guid:str, segments:list[TranscriptSegment]}` with `@property text -> " ".join(seg.text ...)`
  - `EpisodeSummary{episode_guid:str, title:str, order_index:int, key_points:list[str], themes:list[str], notable_quotes:list[str], timeline_markers:list[str]}`
  - `ArcBeat{heading:str, episode_guids:list[str], narrative:str}`
  - `ArcOutline{title:str, throughline:str, beats:list[ArcBeat]}`
  - `ScriptSegment{speaker:str, text:str}` with `@property word_count`
  - `Script{segments:list[ScriptSegment]}` with `@property word_count` and `estimated_minutes(wpm:int)->float`
  - `Chapter{title:str, start_s:float}`; `ShowNotes{summary:str, chapters:list[Chapter]}`
  - `JobOptions{episode_ids:list[str], host_count:int=1, clone:bool=False, target_minutes:int=30}`

- [ ] **Step 1: Failing test** — assert `Transcript.text` joins segments; `Script.word_count` sums; `Script.estimated_minutes(130)` correct; enums have expected members.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `enums.py` then `domain.py`** exactly per interfaces above.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** `Add domain models and enums`.

---

## Task 3: Storage port + filesystem impl

**Files:** Create `src/repodify/storage/base.py`, `storage/filesystem.py`, `tests/unit/storage/test_filesystem.py`

**Interfaces:**
- `class Storage(Protocol)`: `put_bytes(key:str, data:bytes)->str`, `get_bytes(key:str)->bytes`, `put_file(key:str, src:Path)->str`, `local_path(key:str)->Path`, `exists(key:str)->bool`. Returned `str` is a storage URI (`file://` absolute).
- `FilesystemStorage(root: Path)` implements it; creates parent dirs on write.

- [ ] **Step 1: Failing test** — round-trip `put_bytes`/`get_bytes`; `put_file` copies; `exists` reflects state; `local_path` under root.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add storage port and filesystem backend`.

---

## Task 4: Ingest — resolvers (link → RSS URL)

**Files:** Create `src/repodify/ingest/resolvers.py`, `tests/unit/ingest/test_resolvers.py`

**Interfaces:**
- `class Resolver(Protocol)`: `matches(url:str)->bool`, `resolve(url:str, http:httpx.Client)->str` (returns RSS feed URL).
- `RawRssResolver` (matches when URL ends `.xml`/`.rss` or content-type is xml → returns as-is).
- `ApplePodcastsResolver` (matches `podcasts.apple.com`; extract id `id(\d+)`; call `https://itunes.apple.com/lookup?id=...` → `results[0].feedUrl`).
- `CastboxResolver` (matches `castbox.fm`; fetch page HTML; extract feed URL from `<link type="application/rss+xml">` or embedded JSON).
- `resolve(url, http)->str` tries resolvers in registry order; raises `UnresolvableFeedError` if none match.

- [ ] **Step 1: Failing tests** using `respx` to mock httpx: Apple lookup returns feedUrl; raw `.xml` passthrough; unknown raises `UnresolvableFeedError`.
- [ ] **Step 2: FAIL. Step 3: Implement resolvers + registry + error. Step 4: PASS. Step 5: Commit** `Add feed resolvers for raw RSS, Apple, Castbox`.

---

## Task 5: Ingest — feed parsing

**Files:** Create `src/repodify/ingest/feed.py`, `tests/fixtures/sample_feed.xml`, `tests/unit/ingest/test_feed.py`

**Interfaces:**
- `parse_feed(source_url:str, rss_url:str, data:bytes)->Feed`. Uses `feedparser`. Episodes sorted oldest-first, `order_index` assigned 0..n. `audio_url` from first `enclosure`. `is_short_or_trailer` heuristic: `duration_s < 120` OR title matches `(?i)\b(trailer|teaser|bonus|intro)\b`. Entries without audio enclosure are dropped.

- [ ] **Step 1: Create `sample_feed.xml`** — 4 items incl. one trailer, varying pubDates, one without enclosure.
- [ ] **Step 2: Failing test** — 3 episodes parsed (no-enclosure dropped), oldest-first, `order_index` monotonic, trailer flagged.
- [ ] **Step 3: FAIL. Step 4: Implement. Step 5: PASS. Step 6: Commit** `Add RSS feed parsing into domain Episodes`.

---

## Task 6: Ingest — download

**Files:** Create `src/repodify/ingest/download.py`, `tests/unit/ingest/test_download.py`

**Interfaces:**
- `download_episode(episode:Episode, storage:Storage, http:httpx.Client, job_id:str)->str` — streams `episode.audio_url` to `storage` key `f"{job_id}/audio/{episode.order_index}.mp3"`, returns storage URI. Raises `DownloadError` on non-200.

- [ ] **Step 1: Failing test** — respx streams bytes; assert stored bytes match; non-200 → `DownloadError`.
- [ ] **Step 2: FAIL. Step 3: Implement (stream via `http.stream`). Step 4: PASS. Step 5: Commit** `Add streamed episode download`.

---

## Task 7: Transcriber port + fake + faster-whisper

**Files:** Create `src/repodify/ports/transcriber.py`, `src/repodify/transcribe/faster_whisper.py`, `tests/unit/ports/test_transcriber_fake.py`

**Interfaces:**
- `class Transcriber(Protocol)`: `transcribe(audio_path:Path, language:str="en")->Transcript`.
- `FakeTranscriber(canned: dict[str,Transcript] | Transcript)` — returns canned transcript (keyed by filename or constant). Lives in `ports/transcriber.py` for reuse.
- `FasterWhisperTranscriber(model_size:str, device:str="cuda", compute_type:str="float16")` — **lazy import** `from faster_whisper import WhisperModel` inside `__init__`; `transcribe` maps segments → `TranscriptSegment` and sets `episode_guid=""` (caller fills). Uses VAD filter.

- [ ] **Step 1: Failing test** — `FakeTranscriber` returns the canned `Transcript`; protocol satisfied (`isinstance`-free duck test).
- [ ] **Step 2: FAIL. Step 3: Implement port + fake + real (lazy). Step 4: PASS. Step 5: Commit** `Add transcriber port, fake, and faster-whisper backend`.

---

## Task 8: LLM port + Anthropic impl + fake

**Files:** Create `src/repodify/ports/llm.py`, `tests/unit/ports/test_llm_fake.py`

**Interfaces:**
- `class StructuredLLM(Protocol)`: `generate(system:str, user:str, schema:type[T])->T` (T bound to `pydantic.BaseModel`).
- `AnthropicStructuredLLM(model:str, api_key:str)` — wraps `langchain_anthropic.ChatAnthropic(...).with_structured_output(schema)`; `generate` invokes with a system+human message. **Lazy import** of `ChatAnthropic`.
- `FakeStructuredLLM(responses: list[BaseModel])` — pops responses FIFO; records calls in `.calls: list[tuple[str,str,type]]`; raises if exhausted.

- [ ] **Step 1: Failing test** — `FakeStructuredLLM([EpisodeSummary(...)]).generate(...)` returns it and records the call.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add StructuredLLM port with Anthropic and fake backends`.

---

## Task 9: Summarize — map (per-episode)

**Files:** Create `src/repodify/summarize/prompts.py`, `summarize/chains.py`, `tests/unit/summarize/test_summarize_episode.py`

**Interfaces:**
- `summarize_episode(transcript:Transcript, title:str, order_index:int, llm:StructuredLLM)->EpisodeSummary`. Builds system+user prompt from `prompts.EPISODE_SYSTEM`/`EPISODE_USER.format(...)`, calls `llm.generate(system, user, EpisodeSummary)`, forces `episode_guid/title/order_index` onto the result.

- [ ] **Step 1: Failing test** — with `FakeStructuredLLM`, returns summary with correct `episode_guid/order_index`; asserts transcript text is in the user prompt (via `.calls`).
- [ ] **Step 2: FAIL. Step 3: Implement prompts + function. Step 4: PASS. Step 5: Commit** `Add per-episode summarization`.

---

## Task 10: Summarize — reduce (arc)

**Files:** Modify `summarize/chains.py`; create `tests/unit/summarize/test_synthesize_arc.py`

**Interfaces:**
- `synthesize_arc(summaries:list[EpisodeSummary], llm:StructuredLLM)->ArcOutline`. Summaries sorted by `order_index`; prompt instructs chronological throughline; returns `ArcOutline`.

- [ ] **Step 1: Failing test** — with fake, produces `ArcOutline`; prompt contains episodes in ascending order.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add cross-episode arc synthesis`.

---

## Task 11: Script writer

**Files:** Create `src/repodify/script/writer.py`, `tests/unit/script/test_writer.py`

**Interfaces:**
- `write_script(arc:ArcOutline, llm:StructuredLLM, target_minutes:int, wpm:int, host_count:int=1)->Script`. Passes `word_budget = target_minutes*wpm` into the prompt. Phase 1: `host_count==1` → all segments `speaker="narrator"`. Validates result is non-empty; logs a warning if `abs(word_count - word_budget)/word_budget > 0.25`.

- [ ] **Step 1: Failing test** — with fake returning a `Script`, `write_script(..., target_minutes=30, wpm=130)` includes `"3900"` in the prompt; returns the Script.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add single-narrator script writer`.

---

## Task 12: TTS port + fake + F5-TTS

**Files:** Create `src/repodify/ports/tts.py`, `src/repodify/synth/f5_tts.py`, `tests/unit/ports/test_tts_fake.py`

**Interfaces:**
- `class Voice(BaseModel)`: `name:str`, `ref_audio_path:Path|None=None`, `ref_text:str|None=None`.
- `class TTS(Protocol)`: `synthesize(text:str, voice:Voice)->bytes` (returns WAV bytes, 24kHz mono).
- `FakeTTS(sample_rate:int=24000)` — returns a valid WAV whose duration ≈ `len(text.split())/130*60` seconds of silence, built with stdlib `wave` + `struct`. Lives in `ports/tts.py`.
- `F5TTS(...)` — **lazy import** of F5-TTS API; `synthesize` runs the model with `voice.ref_audio_path`/`ref_text`; returns WAV bytes.

- [ ] **Step 1: Failing test** — `FakeTTS().synthesize("one two three", Voice(name="n"))` returns bytes parseable by `wave.open`, correct channels/framerate, duration > 0.
- [ ] **Step 2: FAIL. Step 3: Implement port + fake + real (lazy). Step 4: PASS. Step 5: Commit** `Add TTS port, fake, and F5-TTS backend`.

---

## Task 13: Assemble — synthesize script + stitch + show notes

**Files:** Create `src/repodify/synth/assemble.py`, `tests/unit/synth/test_assemble.py`

**Interfaces:**
- `synthesize_script(script:Script, tts:TTS, voices:dict[str,Voice])->list[bytes]` — one WAV per segment using `voices[segment.speaker]`.
- `assemble_wav(segments:list[bytes])->bytes` — concatenates WAV byte blobs into one WAV (stdlib `wave`; assert uniform format).
- `build_show_notes(arc:ArcOutline, script:Script, segments:list[bytes])->ShowNotes` — summary from `arc.throughline`; one chapter per arc beat with cumulative start time computed from segment durations.
- `wav_to_mp3(wav:bytes, out:Path)->None` — ffmpeg via `subprocess`; **not covered by unit tests** (documented as GPU/host path).

- [ ] **Step 1: Failing test** — from two `FakeTTS` segments, `assemble_wav` yields a WAV whose frame count == sum of inputs; `build_show_notes` chapters count == beats count and start times ascending.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add script synthesis, WAV assembly, and show notes`.

---

## Task 14: Persistence — DB models + repository

**Files:** Create `src/repodify/models/db.py`, `src/repodify/persistence/engine.py`, `persistence/repo.py`, `tests/unit/persistence/test_repo.py`

**Interfaces:**
- ORM: `Job{id:str pk, feed_url:str, status:str, current_stage:str|None, options_json:str, report_json:str, created_at, finished_at|None}`, `StageStatus{id, job_id fk, stage:str, state:str, detail:str|None, started_at|None, finished_at|None}`, `Artifact{id, job_id fk, kind:str, episode_guid:str|None, uri:str, created_at}`.
- `make_engine(database_url:str)`, `init_db(engine)`, `session_factory(engine)`.
- `JobRepository(session_factory)`: `create_job(feed_url, options)->str`, `get_job(job_id)->Job`, `set_status(job_id, JobStatus)`, `start_stage(job_id, StageName)`, `finish_stage(job_id, StageName, StageState, detail=None)`, `add_artifact(job_id, kind, uri, episode_guid=None)`, `set_report(job_id, dict)`.

- [ ] **Step 1: Failing test** (SQLite tmp file) — create job; start/finish a stage; artifact persists; `get_job` reflects status.
- [ ] **Step 2: FAIL. Step 3: Implement ORM + engine + repo. Step 4: PASS. Step 5: Commit** `Add persistence layer and job repository`.

---

## Task 15: Pipeline — state, deps, nodes, graph

**Files:** Create `src/repodify/pipeline/state.py`, `pipeline/nodes.py`, `pipeline/graph.py`, `tests/integration/test_pipeline_end_to_end.py`

**Interfaces:**
- `PipelineState(TypedDict, total=False)`: `job_id, options(JobOptions), feed(Feed), selected(list[Episode]), transcripts(dict[str,Transcript]), summaries(list[EpisodeSummary]), arc(ArcOutline), script(Script), output_uri(str), report(dict)`.
- `@dataclass Deps`: `resolver_resolve:Callable`, `http:httpx.Client`, `storage:Storage`, `transcriber:Transcriber`, `llm_map:StructuredLLM`, `llm_reduce:StructuredLLM`, `tts:TTS`, `voices:dict[str,Voice]`, `repo:JobRepository`, `settings:Settings`.
- Node functions in `nodes.py` (closures via `make_nodes(deps)`): `resolve_node`, `download_node` (transcribe folded in per episode), `summarize_node`, `arc_node`, `script_node`, `synth_node`. Each wraps its stage in `repo.start_stage/finish_stage`; per-episode download/transcribe failures are caught, recorded to `report`, and skipped (not fatal) — if **all** episodes fail, the stage is `FAILED`.
- `build_graph(deps)->CompiledGraph` — linear edges resolve→download→summarize→arc→script→synth; `MemorySaver` checkpointer (Postgres saver selected in worker for prod).

- [ ] **Step 1: Failing integration test** — build `Deps` from all fakes (`FakeTranscriber`, `FakeStructuredLLM` queued with per-episode summaries + arc, another for script, `FakeTTS`, `FilesystemStorage(tmp)`, real `JobRepository` on SQLite, resolver stubbed to a local `sample_feed.xml`, http mocked with respx for downloads). Invoke graph with 2 selected episodes. Assert: `output_uri` exists and is a valid WAV; all 6 stages recorded `DONE`; an `output_audio` artifact is attached.
- [ ] **Step 2: FAIL. Step 3: Implement state + nodes + graph. Step 4: PASS. Step 5: Commit** `Add LangGraph pipeline wiring end to end`.

---

## Task 16: API — schemas, routers, app

**Files:** Create `src/repodify/api/schemas.py`, `api/routers.py`, `api/app.py`, `tests/unit/api/test_api.py`

**Interfaces:**
- Schemas: `ResolveRequest{url}`, `EpisodeOut{...}`, `ResolveResponse{feed_title, rss_url, episodes:list[EpisodeOut]}`, `CreateJobRequest{feed_url, episode_ids:list[str], host_count=1, clone=False, target_minutes=30}`, `JobStatusResponse{id,status,current_stage,stages:list,report}`, `ResultResponse{output_audio_uri, show_notes, chapters}`.
- Routes: `POST /feeds/resolve`, `POST /jobs` (persists via repo, enqueues via injected `enqueue` callable, returns `job_id`), `GET /jobs/{id}`, `GET /jobs/{id}/result` (404 until completed).
- `create_app(repo, resolve_fn, http, enqueue)->FastAPI` factory for testability.

- [ ] **Step 1: Failing test** — FastAPI `TestClient`; `POST /feeds/resolve` (resolver+feed mocked) returns episodes oldest-first; `POST /jobs` returns id and calls the fake `enqueue`; `GET /jobs/{id}` returns status; result 404 before completion.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `Add FastAPI resolve/jobs/result endpoints`.

---

## Task 17: Worker + composition root + docs

**Files:** Create `src/repodify/worker/main.py`; modify `README.md`; create `docker-compose.yml`, `tests/unit/worker/test_compose.py`

**Interfaces:**
- `build_deps(settings:Settings)->Deps` — composition root: picks fakes when `settings.use_fakes`, else real (`FasterWhisperTranscriber`, `AnthropicStructuredLLM` x2, `F5TTS`), always `FilesystemStorage(settings.data_dir)` + `JobRepository`. Ships a default narrator `Voice` (bundled reference clip path from settings).
- `run_job(ctx, job_id)` — arq task: `deps = build_deps(...)`, load job, `build_graph(deps).invoke({...})`, mark completed/failed.
- `WorkerSettings` — `functions=[run_job]`, `redis_settings` from `settings.redis_url`.

- [ ] **Step 1: Failing test** — `build_deps(Settings(use_fakes=True))` returns a `Deps` whose `transcriber` is `FakeTranscriber` and `tts` is `FakeTTS`.
- [ ] **Step 2: FAIL. Step 3: Implement `build_deps` + worker + compose + README run steps (docker-compose up, run api, run worker, curl flow). Step 4: PASS. Step 5: Commit** `Add worker, composition root, and run docs`.

---

## Self-Review

**Spec coverage:**
- §3 flow (resolve→select→run→track→fetch): Tasks 4–6, 15, 16. ✔
- §4 architecture (FastAPI/arq/Postgres/LangGraph/GPU worker): Tasks 15–17. ✔
- §5 stack incl. model tiering (map=Haiku, reduce=Opus): Task 1 settings + Tasks 9/10/17. ✔
- §6 stages (all 8): Tasks 4–13, 15. ✔ (episode-level transcribe folded into download node in Task 15.)
- §7 data model (Job/StageStatus/Artifact/Episode): Tasks 2, 14. ✔
- §8 storage interface + filesystem: Task 3. ✔
- §9 API surface (resolve/jobs/status/result): Task 16. ✔
- §10 progress (StageStatus per node), resumability (checkpointer), partial-failure skip, config: Tasks 14, 15, 1. ✔ (SSE endpoint = deferred, explicitly optional in spec.)
- §12 testing (per-node fakes, one integration, golden length): Tasks 2–17 + 15. ✔ (script length golden = Task 11 warning + assert.)
- §11 phasing: Phase 1 only, by design. Voice-cloning constraints not built here (Phase 3). ✔

**Placeholder scan:** No TBD/TODO; each task has concrete interfaces + test. MP3 export and real GPU/LLM paths are explicitly non-test-gated, not placeholders.

**Type consistency:** `StructuredLLM.generate(system,user,schema)` used identically in Tasks 8–11. `Transcriber.transcribe(audio_path,language)` consistent Tasks 7/15. `TTS.synthesize(text,voice)` consistent Tasks 12/13. `JobRepository` method names match between Tasks 14/15/16. `Deps` field names match Tasks 15/17.

**Deferred (not spec gaps):** SSE progress stream (spec-optional), Postgres checkpointer swap (MemorySaver in tests, Postgres in worker), Castbox scraper fallback (Phase 3), 2-host & cloning (Phases 2/3).
