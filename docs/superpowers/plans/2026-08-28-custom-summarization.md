# Custom Summarization Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users supply optional free-text instructions — one for the whole digest and one per episode — that steer the LLM's summarization, compaction, and time-based cutting.

**Architecture:** Two optional fields on `JobOptions` (`custom_prompt`, `episode_prompts`) flow through the existing map → reduce → script chain. A `with_guidance()` helper appends the user's text as an "Editorial guidance" block: the whole-digest prompt at every LLM stage, the per-episode prompt only at that episode's summarize step. When an episode carries any guidance, the summarizer reads a timestamped rendering of the transcript so time references (e.g. "cut 4:20–6:09") are meaningful. With no prompts, the summarizer input and prompts are byte-for-byte identical to today.

**Tech Stack:** Python 3 (pydantic v2, FastAPI, LangGraph), pytest; React + TypeScript + Vite + Tailwind, vitest + Testing Library + MSW.

## Global Constraints

- Package path is `src/repodify/` (the repo/dir is `repodify`; the Python package is still `repodify`).
- New `JobOptions` / `CreateJobRequest` fields MUST be optional with defaults — existing persisted `options_json` blobs and API clients keep working.
- The no-prompt path MUST be unchanged: same summarizer transcript text and same LLM prompts as today.
- Prompt length cap: `MAX_PROMPT_CHARS = 4000`, applied to both `custom_prompt` and each `episode_prompts` value.
- Web form controls MUST stay native (`<textarea>`, `<input>`) — the dashboard tests assert on native elements.
- Run Python tests with `uv run pytest`; run web tests from `web/` with `npm test`.
- Commit messages: imperative mood, no emojis, no Claude co-authoring. One commit per task.

---

### Task 1: Timestamped transcript renderer

**Files:**
- Modify: `src/repodify/models/domain.py` (add a method to `Transcript`, ~after line 85)
- Test: `tests/unit/models/test_domain.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Transcript.speaker_labeled_text_timestamped() -> str` — like `speaker_labeled_text` but each merged speaker turn is prefixed with its start time as `[MM:SS]`; unlabeled transcripts emit one timestamped line per segment. Also a module-level `_fmt_mmss(seconds: float) -> str`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/models/test_domain.py`:

```python
def test_speaker_labeled_text_timestamped_prefixes_turns():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="hi there", speaker="SPEAKER_00"),
            TranscriptSegment(start=1.0, end=2.0, text="and more", speaker="SPEAKER_00"),
            TranscriptSegment(start=260.0, end=262.0, text="my turn", speaker="SPEAKER_01"),
        ],
    )
    assert t.speaker_labeled_text_timestamped() == (
        "[00:00] SPEAKER_00: hi there and more\n[04:20] SPEAKER_01: my turn"
    )


def test_speaker_labeled_text_timestamped_minutes_over_59():
    t = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=4384.0, end=4386.0, text="late", speaker="SPEAKER_00")],
    )
    assert t.speaker_labeled_text_timestamped() == "[73:04] SPEAKER_00: late"


def test_speaker_labeled_text_timestamped_unlabeled_is_per_segment():
    t = Transcript(
        episode_guid="ep-1",
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="first"),
            TranscriptSegment(start=90.0, end=92.0, text="second"),
        ],
    )
    assert t.speaker_labeled_text_timestamped() == "[00:00] first\n[01:30] second"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/models/test_domain.py -k timestamped -v`
Expected: FAIL with `AttributeError: 'Transcript' object has no attribute 'speaker_labeled_text_timestamped'`

- [ ] **Step 3: Implement the renderer**

In `src/repodify/models/domain.py`, add a module-level helper near the top (after the imports, before the classes):

```python
def _fmt_mmss(seconds: float) -> str:
    """Format a start offset as [MM:SS]; minutes may exceed 59 (e.g. 73:04)."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"
```

Add this method to the `Transcript` class, right after the `speaker_labeled_text` property:

```python
def speaker_labeled_text_timestamped(self) -> str:
    """Like `speaker_labeled_text`, but each merged speaker turn is prefixed
    with its start time as ``[MM:SS]`` so the LLM can honor time references.

    When the transcript carries no speaker labels, each segment is emitted on
    its own timestamped line (keeping time granularity for cut instructions).
    """
    labeled = [s for s in self.segments if s.text.strip()]
    if not labeled:
        return ""
    has_speakers = any(s.speaker for s in labeled)
    lines: list[str] = []
    current_speaker: str | None = None
    for seg in labeled:
        ts = _fmt_mmss(seg.start)
        text = seg.text.strip()
        if not has_speakers:
            lines.append(f"[{ts}] {text}")
            continue
        speaker = seg.speaker or "UNKNOWN"
        if speaker != current_speaker:
            lines.append(f"[{ts}] {speaker}: {text}")
            current_speaker = speaker
        else:
            lines[-1] += " " + text
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/models/test_domain.py -k timestamped -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/models/domain.py tests/unit/models/test_domain.py
git commit -m "Add timestamped transcript rendering for the summarizer"
```

---

### Task 2: JobOptions custom-prompt fields

**Files:**
- Modify: `src/repodify/models/domain.py` (`JobOptions`, ~lines 172-186; imports at line 8)
- Test: `tests/unit/models/test_domain.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `JobOptions.custom_prompt: str | None`, `JobOptions.episode_prompts: dict[str, str]`, module constant `MAX_PROMPT_CHARS = 4000`. `episode_prompts` values are stripped, empties dropped, over-long rejected at validation.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/models/test_domain.py` (add `JobOptions` to the existing domain import at the top of the file, and `import pytest` is already present):

```python
from repodify.models.domain import JobOptions, MAX_PROMPT_CHARS


def test_job_options_defaults_have_no_prompts():
    opts = JobOptions(episode_ids=["ep-1"])
    assert opts.custom_prompt is None
    assert opts.episode_prompts == {}


def test_job_options_episode_prompts_are_stripped_and_emptied():
    opts = JobOptions(
        episode_ids=["ep-1"],
        episode_prompts={"ep-1": "  keep the interview  ", "ep-2": "   "},
    )
    assert opts.episode_prompts == {"ep-1": "keep the interview"}


def test_job_options_rejects_overlong_custom_prompt():
    with pytest.raises(ValueError):
        JobOptions(episode_ids=["ep-1"], custom_prompt="x" * (MAX_PROMPT_CHARS + 1))


def test_job_options_rejects_overlong_episode_prompt():
    with pytest.raises(ValueError):
        JobOptions(episode_ids=["ep-1"], episode_prompts={"ep-1": "x" * (MAX_PROMPT_CHARS + 1)})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/models/test_domain.py -k job_options -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_PROMPT_CHARS'`

- [ ] **Step 3: Implement the fields and validator**

In `src/repodify/models/domain.py`, update the pydantic import (line 8):

```python
from pydantic import BaseModel, Field, field_validator
```

Add a module-level constant near the top (after imports):

```python
MAX_PROMPT_CHARS = 4000
```

Add the two fields to `JobOptions` (after `review_voices` at line 185) and a validator:

```python
    # Free-text editorial guidance layered onto the built-in summarization
    # prompts. `custom_prompt` steers the whole digest (applied at every LLM
    # stage); `episode_prompts` maps an episode guid to guidance applied only to
    # that episode's summary.
    custom_prompt: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS)
    episode_prompts: dict[str, str] = Field(default_factory=dict)

    @field_validator("episode_prompts")
    @classmethod
    def _clean_episode_prompts(cls, value: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for guid, text in value.items():
            text = text.strip()
            if not text:
                continue
            if len(text) > MAX_PROMPT_CHARS:
                raise ValueError(
                    f"episode prompt for {guid} exceeds {MAX_PROMPT_CHARS} chars"
                )
            cleaned[guid] = text
        return cleaned
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/models/test_domain.py -k job_options -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/models/domain.py tests/unit/models/test_domain.py
git commit -m "Add custom_prompt and episode_prompts to JobOptions"
```

---

### Task 3: Prompt composition helpers

**Files:**
- Modify: `src/repodify/summarize/prompts.py`
- Test: `tests/unit/summarize/test_prompt_guidance.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `clean_prompt(s: str | None) -> str | None` — stripped text or `None`.
  - `with_guidance(base_user: str, *, whole: str | None = None, episode: str | None = None) -> str` — returns `base_user` unchanged when neither is meaningful; else appends an "Editorial guidance" block.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/summarize/test_prompt_guidance.py`:

```python
from repodify.summarize.prompts import clean_prompt, with_guidance


def test_clean_prompt_strips_and_nullifies_empty():
    assert clean_prompt("  hi  ") == "hi"
    assert clean_prompt("   ") is None
    assert clean_prompt(None) is None


def test_with_guidance_no_guidance_returns_base_unchanged():
    base = "Base user prompt."
    assert with_guidance(base) is base
    assert with_guidance(base, whole="   ", episode=None) is base


def test_with_guidance_whole_only():
    out = with_guidance("BASE", whole="focus on funding")
    assert out.startswith("BASE")
    assert "Whole digest: focus on funding" in out
    assert "This episode:" not in out


def test_with_guidance_episode_only():
    out = with_guidance("BASE", episode="cut 4:20 to 6:09")
    assert "This episode: cut 4:20 to 6:09" in out
    assert "Whole digest:" not in out


def test_with_guidance_both_are_labeled():
    out = with_guidance("BASE", whole="skip ads", episode="keep the interview")
    assert "Whole digest: skip ads" in out
    assert "This episode: keep the interview" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/summarize/test_prompt_guidance.py -v`
Expected: FAIL with `ImportError: cannot import name 'clean_prompt'`

- [ ] **Step 3: Implement the helpers**

Append to `src/repodify/summarize/prompts.py`:

```python
def clean_prompt(s: str | None) -> str | None:
    """Return the stripped prompt text, or ``None`` when empty/whitespace/None."""
    if s is None:
        return None
    s = s.strip()
    return s or None


_GUIDANCE_HEADER = (
    "Editorial guidance from the user — follow it where it does not conflict "
    "with producing the required structured output. Transcript lines may be "
    "prefixed with a timestamp like [MM:SS]; you may act on time references."
)


def with_guidance(
    base_user: str, *, whole: str | None = None, episode: str | None = None
) -> str:
    """Append an editorial-guidance block to a base user prompt.

    Returns ``base_user`` unchanged when no meaningful guidance is given, so
    callers that pass nothing reproduce the built-in prompt exactly.
    """
    whole = clean_prompt(whole)
    episode = clean_prompt(episode)
    if not whole and not episode:
        return base_user
    lines = [_GUIDANCE_HEADER]
    if whole:
        lines.append(f"- Whole digest: {whole}")
    if episode:
        lines.append(f"- This episode: {episode}")
    return base_user + "\n\n" + "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/summarize/test_prompt_guidance.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/summarize/prompts.py tests/unit/summarize/test_prompt_guidance.py
git commit -m "Add clean_prompt and with_guidance prompt helpers"
```

---

### Task 4: Guidance in the summarize chains

**Files:**
- Modify: `src/repodify/summarize/chains.py`
- Test: `tests/unit/summarize/test_summarize_episode.py`, `tests/unit/summarize/test_synthesize_arc.py`

**Interfaces:**
- Consumes: `prompts.with_guidance`, `prompts.clean_prompt`, `Transcript.speaker_labeled_text_timestamped`.
- Produces:
  - `summarize_episode(transcript, title, order_index, llm, *, whole_prompt=None, episode_prompt=None) -> EpisodeSummary`
  - `synthesize_arc(summaries, llm, *, whole_prompt=None) -> ArcOutline`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/summarize/test_summarize_episode.py`:

```python
from repodify.summarize import prompts


def test_summarize_episode_no_prompts_matches_builtin_exactly():
    # Regression guard: no guidance -> today's exact prompt and untimestamped text.
    transcript = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=5.0, end=6.0, text="the quick brown fox")],
    )
    llm = FakeStructuredLLM([EpisodeSummary(key_points=["p"])])

    summarize_episode(transcript, title="T", order_index=0, llm=llm)

    _system, user, _schema = llm.calls[0]
    expected = prompts.EPISODE_USER.format(
        title="T", transcript=transcript.speaker_labeled_text
    )
    assert user == expected
    assert "[00:05]" not in user  # no timestamps on the default path


def test_summarize_episode_with_prompts_adds_guidance_and_timestamps():
    transcript = Transcript(
        episode_guid="ep-1",
        segments=[TranscriptSegment(start=260.0, end=262.0, text="interview part")],
    )
    llm = FakeStructuredLLM([EpisodeSummary(key_points=["p"])])

    summarize_episode(
        transcript, title="T", order_index=0, llm=llm,
        whole_prompt="skip ads", episode_prompt="cut 4:20 to 6:09",
    )

    _system, user, _schema = llm.calls[0]
    assert "[04:20]" in user            # timestamped transcript
    assert "Whole digest: skip ads" in user
    assert "This episode: cut 4:20 to 6:09" in user
```

Add to `tests/unit/summarize/test_synthesize_arc.py`:

```python
def test_synthesize_arc_appends_whole_prompt():
    summaries = [EpisodeSummary(episode_guid="a", order_index=0, title="First")]
    arc = ArcOutline(title="T", throughline="x", beats=[])
    llm = FakeStructuredLLM([arc])

    synthesize_arc(summaries, llm, whole_prompt="focus on funding")

    _system, user, _schema = llm.calls[0]
    assert "Whole digest: focus on funding" in user
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/summarize -v`
Expected: FAIL — `test_summarize_episode_with_prompts_adds_guidance_and_timestamps` and `test_synthesize_arc_appends_whole_prompt` fail with `TypeError: ... unexpected keyword argument 'whole_prompt'`

- [ ] **Step 3: Implement guidance threading**

Replace `summarize_episode` and `synthesize_arc` in `src/repodify/summarize/chains.py`:

```python
def summarize_episode(
    transcript: Transcript,
    title: str,
    order_index: int,
    llm: StructuredLLM,
    *,
    whole_prompt: str | None = None,
    episode_prompt: str | None = None,
) -> EpisodeSummary:
    """Summarize one episode transcript into a structured `EpisodeSummary`.

    When either prompt carries guidance, the transcript is rendered with
    timestamps so time references are meaningful, and the guidance is appended to
    the user prompt. With no guidance, the input and prompt are unchanged.
    """
    whole = prompts.clean_prompt(whole_prompt)
    episode = prompts.clean_prompt(episode_prompt)
    if whole or episode:
        transcript_text = transcript.speaker_labeled_text_timestamped()
    else:
        transcript_text = transcript.speaker_labeled_text
    user = prompts.EPISODE_USER.format(title=title, transcript=transcript_text)
    user = prompts.with_guidance(user, whole=whole, episode=episode)
    summary = llm.generate(prompts.EPISODE_SYSTEM, user, EpisodeSummary)
    # The model summarizes content; identity fields are authoritative from us.
    return summary.model_copy(
        update={
            "episode_guid": transcript.episode_guid,
            "title": title,
            "order_index": order_index,
        }
    )
```

```python
def synthesize_arc(
    summaries: list[EpisodeSummary],
    llm: StructuredLLM,
    *,
    whole_prompt: str | None = None,
) -> ArcOutline:
    """Combine per-episode summaries into one chronological narrative arc."""
    ordered = sorted(summaries, key=lambda s: s.order_index)
    user = prompts.ARC_USER.format(summaries=_format_summaries(ordered))
    user = prompts.with_guidance(user, whole=whole_prompt)
    return llm.generate(prompts.ARC_SYSTEM, user, ArcOutline)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/summarize -v`
Expected: PASS (all, including the existing chain tests)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/summarize/chains.py tests/unit/summarize/
git commit -m "Thread custom guidance through summarize and arc chains"
```

---

### Task 5: Guidance in the script writer

**Files:**
- Modify: `src/repodify/script/writer.py`
- Test: `tests/unit/script/test_writer.py`

**Interfaces:**
- Consumes: `prompts.with_guidance`.
- Produces: `write_script(arc, llm, target_minutes, wpm, host_count=1, cast=None, *, whole_prompt=None) -> Script`. Guidance is baked into `base_user` before the attempt loop, so it survives expansion retries.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/script/test_writer.py`:

```python
def test_write_script_appends_whole_prompt_and_keeps_it_on_expansion():
    # budget = 2 * 10 = 20 words; floor 15 -> first draft is short, triggers retry.
    short = Script(segments=[ScriptSegment(speaker="narrator", text="too short")])  # 2
    full = Script(
        segments=[ScriptSegment(speaker="narrator", text=" ".join(["word"] * 20))]
    )
    llm = FakeStructuredLLM([short, full])

    write_script(_arc(), llm, target_minutes=2, wpm=10, whole_prompt="skip the ads")

    assert len(llm.calls) == 2
    _s0, user0, _ = llm.calls[0]
    _s1, user1, _ = llm.calls[1]
    assert "Whole digest: skip the ads" in user0   # present on first draft
    assert "Whole digest: skip the ads" in user1   # ...and on the expansion retry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/script/test_writer.py -k whole_prompt -v`
Expected: FAIL with `TypeError: write_script() got an unexpected keyword argument 'whole_prompt'`

- [ ] **Step 3: Implement guidance in the writer**

In `src/repodify/script/writer.py`, update the `write_script` signature (line 74-81) to add the keyword-only param:

```python
def write_script(
    arc: ArcOutline,
    llm: StructuredLLM,
    target_minutes: int,
    wpm: int,
    host_count: int = 1,
    cast: list[Speaker] | None = None,
    *,
    whole_prompt: str | None = None,
) -> Script:
```

Then, immediately after the `if cast is not None: ... else: ...` block that sets `base_user` (i.e. right before `floor = word_budget * (1 - _BUDGET_TOLERANCE)` at line 130), insert:

```python
    # Whole-digest guidance rides on the base prompt so it persists across the
    # expansion retries below (which rebuild `user` from `base_user`).
    base_user = prompts.with_guidance(base_user, whole=whole_prompt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/script/test_writer.py -v`
Expected: PASS (all, including existing writer tests)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/script/writer.py tests/unit/script/test_writer.py
git commit -m "Thread whole-digest guidance through the script writer"
```

---

### Task 6: Wire prompts through the pipeline nodes

**Files:**
- Modify: `src/repodify/pipeline/nodes.py` (`summarize_node` ~lines 198-214, `arc_node` ~lines 216-225, `script_node` ~lines 227-250)
- Test: `tests/integration/test_custom_prompt_pipeline.py` (create)

**Interfaces:**
- Consumes: `state["options"].custom_prompt`, `state["options"].episode_prompts`, the guidance-aware chain/writer functions from Tasks 4–5.
- Produces: no new public interface; nodes now forward prompts to the chains.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_custom_prompt_pipeline.py` (mirrors `test_pipeline_end_to_end.py`'s harness, adding prompt assertions):

```python
import httpx
import respx

from repodify.config import Settings
from repodify.models.domain import (
    ArcBeat,
    ArcOutline,
    EpisodeSummary,
    JobOptions,
    Script,
    ScriptSegment,
    Transcript,
    TranscriptSegment,
)
from repodify.pipeline.graph import build_graph
from repodify.pipeline.state import Deps
from repodify.ports.diarizer import FakeDiarizer
from repodify.ports.llm import FakeStructuredLLM
from repodify.ports.transcoder import FakeTranscoder
from repodify.ports.transcriber import FakeTranscriber
from repodify.ports.tts import FakeTTS, Voice
from repodify.ports.voice_cloner import FakeVoiceCloner
from repodify.ports.watermarker import FakeWatermarker
from repodify.storage.filesystem import FilesystemStorage


def test_pipeline_forwards_custom_prompts_to_llms(tmp_path, sample_feed_xml, repo):
    storage = FilesystemStorage(tmp_path / "data")
    transcriber = FakeTranscriber(
        Transcript(
            episode_guid="",
            segments=[TranscriptSegment(start=260.0, end=263.0, text="spoken words here")],
        )
    )
    llm_map = FakeStructuredLLM(
        [EpisodeSummary(key_points=["p1"]), EpisodeSummary(key_points=["p2"])]
    )
    arc = ArcOutline(
        title="The Arc",
        throughline="How the show evolved.",
        beats=[ArcBeat(heading="B", episode_guids=["ep-1"], narrative="It started.")],
    )
    script = Script(
        segments=[ScriptSegment(speaker="narrator", text=" ".join(["word"] * 200))]
    )
    llm_reduce = FakeStructuredLLM([arc, script])

    options = JobOptions(
        episode_ids=["ep-1", "ep-2"],
        target_minutes=1,
        custom_prompt="skip sponsor reads",
        episode_prompts={"ep-1": "cut 4:20 to 6:09"},
    )
    job_id = repo.create_job("https://castbox.fm/channel/xyz", options)
    settings = Settings(_env_file=None)

    def resolver_resolve(url, http):
        return "https://feed.example.com/feed.xml"

    with respx.mock:
        respx.get("https://feed.example.com/feed.xml").respond(content=sample_feed_xml)
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIO-1")
        respx.get("https://cdn.example.com/ep2.mp3").respond(content=b"AUDIO-2")
        with httpx.Client() as http:
            deps = Deps(
                resolver_resolve=resolver_resolve,
                http=http,
                storage=storage,
                transcriber=transcriber,
                diarizer=FakeDiarizer(),
                transcoder=FakeTranscoder(),
                llm_map=llm_map,
                llm_reduce=llm_reduce,
                tts=FakeTTS(),
                voices={"narrator": Voice(name="narrator")},
                voice_cloner=FakeVoiceCloner(),
                watermarker=FakeWatermarker(),
                repo=repo,
                settings=settings,
            )
            build_graph(deps).invoke(
                {
                    "job_id": job_id,
                    "feed_url": "https://castbox.fm/channel/xyz",
                    "options": options,
                },
                config={"configurable": {"thread_id": job_id}},
            )

    # ep-1's map call has whole + episode guidance and a timestamped transcript.
    ep1_user = llm_map.calls[0][1]
    assert "Whole digest: skip sponsor reads" in ep1_user
    assert "This episode: cut 4:20 to 6:09" in ep1_user
    assert "[04:20]" in ep1_user
    # ep-2 has only the whole-digest guidance (no per-episode note).
    ep2_user = llm_map.calls[1][1]
    assert "Whole digest: skip sponsor reads" in ep2_user
    assert "This episode:" not in ep2_user
    # Arc (reduce call 0) and script (reduce call 1) both carry the whole prompt.
    assert "Whole digest: skip sponsor reads" in llm_reduce.calls[0][1]
    assert "Whole digest: skip sponsor reads" in llm_reduce.calls[1][1]
```

Note: the `sample_feed_xml` fixture uses episode guids `ep-1` and `ep-2` (as in `test_pipeline_end_to_end.py`). If the ordering of `llm_map.calls` differs, assert by searching both calls for the ep-1 markers instead of indexing.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_custom_prompt_pipeline.py -v`
Expected: FAIL — the guidance strings are absent from the captured prompts (nodes don't forward them yet)

- [ ] **Step 3: Wire the nodes**

In `src/repodify/pipeline/nodes.py`, in `summarize_node`, replace the summaries list comprehension (lines 205-208):

```python
            summaries = [
                summarize_episode(
                    transcripts[e.guid], e.title, e.order_index, deps.llm_map,
                    whole_prompt=state["options"].custom_prompt,
                    episode_prompt=state["options"].episode_prompts.get(e.guid),
                )
                for e in ordered
            ]
```

In `arc_node`, replace the `synthesize_arc` call (line 220):

```python
            arc = synthesize_arc(
                state["summaries"], deps.llm_reduce,
                whole_prompt=state["options"].custom_prompt,
            )
```

In `script_node`, add `whole_prompt` to the `write_script` call (lines 237-244):

```python
            script = write_script(
                state["arc"],
                deps.llm_reduce,
                target_minutes=options.target_minutes,
                wpm=deps.settings.wpm,
                host_count=options.host_count,
                cast=cast if options.preserve_speakers else None,
                whole_prompt=options.custom_prompt,
            )
```

(`options = state["options"]` is already bound at the top of `script_node`; `summarize_node` and `arc_node` read `state["options"]` directly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_custom_prompt_pipeline.py tests/integration/test_pipeline_end_to_end.py -v`
Expected: PASS (both — the new wiring test and the unchanged end-to-end test)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/pipeline/nodes.py tests/integration/test_custom_prompt_pipeline.py
git commit -m "Forward custom prompts from pipeline nodes to the LLM chains"
```

---

### Task 7: Accept prompts in the API

**Files:**
- Modify: `src/repodify/api/schemas.py` (`CreateJobRequest`, ~lines 31-39), `src/repodify/api/app.py` (`create_job`, ~lines 89-102)
- Test: `tests/unit/api/test_api.py`

**Interfaces:**
- Consumes: `JobOptions.custom_prompt`, `JobOptions.episode_prompts`.
- Produces: `CreateJobRequest.custom_prompt: str | None`, `CreateJobRequest.episode_prompts: dict[str, str]`, persisted into the job's `JobOptions`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/api/test_api.py`:

```python
def test_create_job_persists_custom_prompts(repo, tmp_path):
    with httpx.Client() as http:
        client = TestClient(_app(repo, http, tmp_path))
        resp = client.post(
            "/jobs",
            json={
                "feed_url": "https://feed",
                "episode_ids": ["ep-1"],
                "custom_prompt": "skip sponsor reads",
                "episode_prompts": {"ep-1": "keep the interview"},
            },
        )
    assert resp.status_code == 200
    options = JobOptions.model_validate_json(repo.get_job(resp.json()["job_id"]).options_json)
    assert options.custom_prompt == "skip sponsor reads"
    assert options.episode_prompts == {"ep-1": "keep the interview"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/api/test_api.py -k custom_prompts -v`
Expected: FAIL — `options.custom_prompt` is `None` (request fields are ignored / not present)

- [ ] **Step 3: Implement the schema + passthrough**

In `src/repodify/api/schemas.py`, add two fields to `CreateJobRequest` (after `review_voices` at line 39):

```python
    custom_prompt: str | None = None
    episode_prompts: dict[str, str] = {}
```

In `src/repodify/api/app.py`, extend the `JobOptions(...)` construction in `create_job` (lines 91-99):

```python
        options = JobOptions(
            episode_ids=req.episode_ids,
            host_count=req.host_count,
            clone=req.clone,
            target_minutes=req.target_minutes,
            voice_assignments=req.voice_assignments,
            preserve_speakers=req.preserve_speakers,
            review_voices=req.review_voices,
            custom_prompt=req.custom_prompt,
            episode_prompts=req.episode_prompts,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/api/test_api.py -v`
Expected: PASS (all, including the new test)

- [ ] **Step 5: Commit**

```bash
git add src/repodify/api/schemas.py src/repodify/api/app.py tests/unit/api/test_api.py
git commit -m "Accept custom_prompt and episode_prompts in the create-job API"
```

---

### Task 8: Per-episode note field in the web EpisodePicker

**Files:**
- Modify: `web/src/api/types.ts` (`CreateJobRequest`, ~lines 23-32), `web/src/components/EpisodePicker.tsx`
- Test: `web/src/components/EpisodePicker.test.tsx` (create)

**Interfaces:**
- Consumes: nothing new from Python.
- Produces:
  - `CreateJobRequest` gains `custom_prompt?: string | null` and `episode_prompts?: Record<string, string>`.
  - `EpisodePicker` gains props `prompts: Record<string, string>` and `onPromptChange: (guid: string, value: string) => void`; each selected episode shows an "add note"/"note" toggle revealing a native `<textarea aria-label={`Note for ${ep.title}`}>`.

- [ ] **Step 1: Extend the request type**

In `web/src/api/types.ts`, add to the `CreateJobRequest` interface (after `review_voices?: boolean`):

```ts
  custom_prompt?: string | null
  episode_prompts?: Record<string, string>
```

- [ ] **Step 2: Write the failing test**

Create `web/src/components/EpisodePicker.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { EpisodePicker } from './EpisodePicker'
import type { EpisodeOut } from '../api/types'

const EP: EpisodeOut = {
  guid: 'e1', title: 'Ep One', published_at: null,
  duration_s: 60, order_index: 0, is_short_or_trailer: false,
}

function Harness() {
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  return (
    <EpisodePicker
      episodes={[EP]}
      selected={new Set(['e1'])}
      onToggle={() => {}}
      prompts={prompts}
      onPromptChange={(guid, value) => setPrompts((p) => ({ ...p, [guid]: value }))}
    />
  )
}

describe('EpisodePicker per-episode notes', () => {
  it('reveals a note textarea for a selected episode and records typed text', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    // Textarea hidden until the note is opened.
    expect(screen.queryByLabelText(/note for ep one/i)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /add note/i }))
    const box = screen.getByLabelText(/note for ep one/i)
    await user.type(box, 'keep the interview')
    expect(box).toHaveValue('keep the interview')
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `web/`): `npm test -- EpisodePicker`
Expected: FAIL — `EpisodePicker` doesn't accept `prompts`/`onPromptChange` and renders no note control.

- [ ] **Step 4: Implement the note accordion**

Replace `web/src/components/EpisodePicker.tsx` with:

```tsx
import { useState } from 'react'
import type { EpisodeOut } from '../api/types'
import { cn } from '../lib/utils'
import { Badge } from './ui/badge'
import { Checkbox } from './ui/checkbox'

function formatDuration(seconds: number | null): string | null {
  if (!seconds) return null
  const mins = Math.round(seconds / 60)
  if (mins < 60) return `${mins} min`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString()
}

export function EpisodePicker({
  episodes,
  selected,
  onToggle,
  prompts,
  onPromptChange,
}: {
  episodes: EpisodeOut[]
  selected: Set<string>
  onToggle: (guid: string) => void
  prompts: Record<string, string>
  onPromptChange: (guid: string, value: string) => void
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())

  function toggleOpen(guid: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(guid)) next.delete(guid)
      else next.add(guid)
      return next
    })
  }

  return (
    <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
      {episodes.map((ep) => {
        const isSelected = selected.has(ep.guid)
        const isOpen = open.has(ep.guid)
        const hasNote = Boolean(prompts[ep.guid]?.trim())
        const meta = [formatDate(ep.published_at), formatDuration(ep.duration_s)].filter(Boolean)
        return (
          <li key={ep.guid}>
            <label
              className={cn(
                'flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition-colors',
                isSelected
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-border hover:bg-muted/50',
              )}
            >
              <Checkbox
                aria-label={ep.title}
                checked={isSelected}
                onChange={() => onToggle(ep.guid)}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{ep.title}</span>
                {meta.length > 0 && (
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {meta.join(' · ')}
                  </span>
                )}
              </span>
              {ep.is_short_or_trailer && <Badge variant="secondary">trailer</Badge>}
            </label>

            {isSelected && (
              <div className="mt-1 pl-8">
                <button
                  type="button"
                  onClick={() => toggleOpen(ep.guid)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {isOpen ? '▾' : '▸'} {hasNote ? 'note' : 'add note'}
                </button>
                {isOpen && (
                  <textarea
                    aria-label={`Note for ${ep.title}`}
                    value={prompts[ep.guid] ?? ''}
                    onChange={(e) => onPromptChange(ep.guid, e.target.value)}
                    placeholder="e.g. keep only the interview; cut 4:20 to 6:09"
                    rows={2}
                    className={cn(
                      'mt-1 flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm transition-colors',
                      'placeholder:text-muted-foreground/70',
                      'focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40',
                    )}
                  />
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `web/`): `npm test -- EpisodePicker`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add web/src/api/types.ts web/src/components/EpisodePicker.tsx web/src/components/EpisodePicker.test.tsx
git commit -m "Add per-episode note field to the EpisodePicker"
```

---

### Task 9: Custom-instructions field and submission in NewDigest

**Files:**
- Modify: `web/src/routes/NewDigest.tsx`
- Test: `web/src/routes/NewDigest.test.tsx`

**Interfaces:**
- Consumes: `EpisodePicker`'s `prompts`/`onPromptChange` props (Task 8), `CreateJobRequest` fields (Task 8).
- Produces: no new interface; the create-job body now includes `custom_prompt` (when non-empty) and `episode_prompts` (selected + non-empty only).

- [ ] **Step 1: Write the failing test**

Replace the body of `web/src/routes/NewDigest.test.tsx`'s test and add a second test that captures the POST body. Full file:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
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

const RESOLVE = http.post('/feeds/resolve', () =>
  HttpResponse.json({
    feed_title: 'Show',
    rss_url: 'https://x/rss',
    episodes: [
      { guid: 'e1', title: 'Ep One', published_at: null, duration_s: 60, order_index: 0, is_short_or_trailer: false },
    ],
  }),
)

describe('NewDigest', () => {
  it('resolves a feed, lists episodes, and creates a job', async () => {
    server.use(RESOLVE, http.post('/jobs', () => HttpResponse.json({ job_id: 'job-1' })))
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText(/feed url/i), 'https://x')
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    await waitFor(() => expect(screen.getByText('Ep One')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    await user.click(screen.getByRole('button', { name: /create digest/i }))
    await waitFor(() => expect(screen.getByText(/job-1/)).toBeInTheDocument())
  })

  it('submits custom_prompt and per-episode episode_prompts', async () => {
    let body: any = null
    server.use(
      RESOLVE,
      http.post('/jobs', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ job_id: 'job-2' })
      }),
    )
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText(/feed url/i), 'https://x')
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    await waitFor(() => expect(screen.getByText('Ep One')).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /ep one/i }))
    await user.type(screen.getByLabelText(/custom instructions/i), 'skip sponsor reads')
    await user.click(screen.getByRole('button', { name: /add note/i }))
    await user.type(screen.getByLabelText(/note for ep one/i), 'keep the interview')
    await user.click(screen.getByRole('button', { name: /create digest/i }))

    await waitFor(() => expect(body).not.toBeNull())
    expect(body.custom_prompt).toBe('skip sponsor reads')
    expect(body.episode_prompts).toEqual({ e1: 'keep the interview' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `web/`): `npm test -- NewDigest`
Expected: FAIL — no "Custom instructions" field / `body.custom_prompt` is undefined.

- [ ] **Step 3: Implement the field and submission wiring**

In `web/src/routes/NewDigest.tsx`:

Add two state hooks after `const [reviewVoices, setReviewVoices] = useState(false)` (line 19):

```tsx
  const [customPrompt, setCustomPrompt] = useState('')
  const [episodePrompts, setEpisodePrompts] = useState<Record<string, string>>({})
```

Replace `onCreate` (lines 33-42) with:

```tsx
  async function onCreate() {
    const episode_prompts: Record<string, string> = {}
    for (const guid of selected) {
      const note = episodePrompts[guid]?.trim()
      if (note) episode_prompts[guid] = note
    }
    const { job_id } = await create.mutateAsync({
      feed_url: url,
      episode_ids: [...selected],
      host_count: hostCount,
      target_minutes: targetMinutes,
      review_voices: reviewVoices,
      custom_prompt: customPrompt.trim() || undefined,
      episode_prompts,
    })
    navigate(`/jobs/${job_id}`)
  }
```

Pass the new props to `EpisodePicker` (line 107):

```tsx
            <EpisodePicker
              episodes={resolve.data.episodes}
              selected={selected}
              onToggle={toggle}
              prompts={episodePrompts}
              onPromptChange={(guid, value) =>
                setEpisodePrompts((prev) => ({ ...prev, [guid]: value }))
              }
            />
```

Add the custom-instructions textarea inside the format `<div>` — insert it right after the closing `</label>` of the "Assign voices per speaker" checkbox (after line 144), as a full-width block so it sits under the row:

```tsx
              <label className="w-full space-y-1.5">
                <span className="block text-sm font-medium">Custom instructions</span>
                <textarea
                  aria-label="Custom instructions"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  placeholder="Steer the whole digest — e.g. focus on the funding news; skip sponsor reads. You can reference times like 4:20."
                  rows={3}
                  className="flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm transition-colors placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                />
                <span className="block text-xs text-muted-foreground">
                  Optional. Leave blank to use the default summary.
                </span>
              </label>
```

Because the parent row is `sm:flex-wrap`, the `w-full` label wraps onto its own line beneath Target length / Hosts / the checkbox.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `web/`): `npm test -- NewDigest`
Expected: PASS (2 passed)

- [ ] **Step 5: Full web + Python suites**

Run (from `web/`): `npm test`
Expected: PASS (all)
Run (from repo root): `uv run pytest`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/NewDigest.tsx web/src/routes/NewDigest.test.tsx
git commit -m "Add custom instructions field and prompt submission to NewDigest"
```

---

## Self-Review Notes

- **Spec coverage:** timestamped renderer (Task 1) ↔ spec §2; JobOptions fields + validation (Task 2) ↔ §1/§4; `with_guidance`/`clean_prompt` (Task 3) ↔ §3; chain threading (Task 4) ↔ §4; script writer (Task 5) ↔ §5; node wiring + pipeline test (Task 6) ↔ §6 + Testing; API (Task 7) ↔ §7; web types + EpisodePicker + NewDigest (Tasks 8–9) ↔ §8 + Testing. The no-prompt regression guard lives in Task 4 Step 1 (`test_summarize_episode_no_prompts_matches_builtin_exactly`).
- **Naming consistency:** `custom_prompt`/`episode_prompts` (Python + `snake_case` JSON), `whole_prompt`/`episode_prompt` (chain kwargs), `with_guidance(base_user, *, whole=, episode=)`, `speaker_labeled_text_timestamped()`, `MAX_PROMPT_CHARS`, `clean_prompt` — used identically across tasks.
- **Deviation from spec:** the spec suggested factoring a shared turn-grouping helper between `speaker_labeled_text` and the timestamped renderer. The two genuinely differ in their unlabeled fallback, so Task 1 implements the timestamped renderer standalone and leaves the existing property untouched (simpler, no behavior change to the default path).
</content>
