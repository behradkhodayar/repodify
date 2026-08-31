# Custom summarization prompts (issue #33)

## Goal

Today the summarization pipeline runs one fixed editorial policy: the built-in
prompts in `summarize/prompts.py` decide what each episode summary keeps, how the
cross-episode arc is shaped, and how the spoken script reads. Users cannot steer
any of it.

Let a user optionally supply free-text instructions that steer the LLM:

- A **whole-digest** instruction (e.g. "focus on the funding news; skip sponsor
  reads") that applies across the run.
- A **per-episode** instruction (e.g. "keep only the interview, cut the ads" or
  "drop the section from 4:20 to 6:09") that applies to a single episode.

Both are optional. With neither supplied, the pipeline behaves exactly as it does
today — the summarizer input, prompts, and output are byte-for-byte unchanged.

## Non-goals

- **Deterministic audio/transcript trimming.** Time references are honored
  best-effort by the LLM, not by slicing audio or transcript segments at exact
  timestamps. Frame-exact cutting is a separate, larger feature.
- **Parsing durations/times out of free text** to drive length. The existing
  `target_minutes` control still drives the hard word budget in the script stage.
  A custom prompt is qualitative guidance layered on top; it does not override
  `target_minutes`.
- **Replacing the built-in prompts.** User text *augments* the defaults; the
  pipeline still produces the same structured output (`key_points`, `themes`,
  `beats`, script `segments`). No "raw prompt" mode.
- **Propagating per-episode instructions past the map step.** A per-episode
  instruction shapes that episode's summary; the arc and script build on the
  already-shaped summaries, so nothing further is threaded through.
- **Persisting the prompts into show notes.** They already live in the job's
  `options_json`; surfacing them in the UI/show notes can come later (YAGNI).

## Approach

Two levers, layered onto the existing map → reduce → script chain:

1. **Whole-digest guidance** is appended as an "Editorial guidance" block to the
   user prompt at **every** LLM stage — per-episode summarize (map), arc
   synthesis (reduce), and script writing — so a policy like "skip ads" is
   honored from the first extraction through to the spoken script.

2. **Per-episode guidance** is appended only at that episode's **summarize (map)**
   step, alongside the whole-digest block.

To make time references meaningful, the summarizer reads a **timestamped**
rendering of the transcript (each merged speaker turn prefixed with its start
time, `[MM:SS]`) — but only for episodes that actually carry custom guidance.
Episodes with no guidance keep using today's untimestamped
`speaker_labeled_text`, so the default path is untouched.

Guidance is folded into the *base* user prompt (not appended after the fact) so
it survives the script writer's expand-retry loop, which rebuilds the user prompt
from `base_user` on each attempt.

`JobOptions` is a pydantic model persisted as a JSON blob (`options_json`), so
two new optional fields deserialize cleanly on existing jobs.

## Changes

### 1. Domain model — `src/repodify/models/domain.py`

Add a module-level constant and two optional fields to `JobOptions`:

```python
MAX_PROMPT_CHARS = 4000

# Free-text editorial guidance layered onto the built-in summarization prompts.
# `custom_prompt` steers the whole digest (every LLM stage); `episode_prompts`
# maps an episode guid to guidance applied only to that episode's summary.
custom_prompt: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS)
episode_prompts: dict[str, str] = Field(default_factory=dict)
```

A `field_validator` on `episode_prompts` strips each value, drops empties, and
rejects any value longer than `MAX_PROMPT_CHARS`. The `custom_prompt` bound is the
same constant, enforced by the field constraint above.

**Meaningful-guidance cleaning.** Treat `None`/empty/whitespace as "no guidance".
A free function `clean_prompt(s: str | None) -> str | None` in
`summarize/prompts.py` returns the stripped text or `None`. Cleaning happens
**inside** `with_guidance` and the chain/writer functions, so callers (the
pipeline nodes) pass raw option values without pre-checking them.

### 2. Transcript rendering — `src/repodify/models/domain.py`

`speaker_labeled_text` stays as-is (a property, one caller). Add a sibling method
that renders the same speaker-grouped text with a leading timestamp per turn:

```python
def speaker_labeled_text_timestamped(self) -> str:
    """Like `speaker_labeled_text`, but each merged speaker turn is prefixed
    with its start time as `[MM:SS]` so the LLM can honor time references."""
```

Rules:
- Same grouping logic as `speaker_labeled_text` (merge consecutive same-speaker
  segments).
- Prefix each emitted line with `[MM:SS]` computed from the first segment's
  `start` of that turn. `MM` may exceed 59 for long episodes (e.g. `[73:04]`) —
  format as total minutes, zero-padded seconds.
- When no segment carries a speaker label, still emit timestamped lines (one per
  segment or per contiguous run) rather than falling back to plain text, so a
  single-narrator source transcript is still time-referenceable.

Factor the shared grouping so the two renderings don't duplicate logic: a private
helper yields `(speaker, start, text)` turns; each public renderer formats them.

### 3. Prompt composition — `src/repodify/summarize/prompts.py`

Add a helper that appends guidance to a base user prompt:

```python
def with_guidance(base_user: str, *, whole: str | None = None,
                  episode: str | None = None) -> str:
    """Append an editorial-guidance section to a base user prompt.

    Returns `base_user` unchanged when no guidance is given, so callers that pass
    nothing produce today's exact prompt."""
```

Block format (only non-empty parts are emitted):

```
Editorial guidance from the user — follow it where it does not conflict with
producing the required structured output:
- Whole digest: {whole}
- This episode: {episode}
```

Timestamps in the transcript are referenced by a short note the block adds only
when `episode`/`whole` is present *and* the transcript is timestamped — but to
keep this simple, the block always tells the model that transcript lines may be
timestamped `[MM:SS]` and it may act on time references. (Cheap, harmless when no
times are mentioned.)

### 4. Summarization chain — `src/repodify/summarize/chains.py`

`summarize_episode` gains optional guidance params and picks the transcript
rendering accordingly:

```python
def summarize_episode(
    transcript, title, order_index, llm,
    *, whole_prompt: str | None = None, episode_prompt: str | None = None,
) -> EpisodeSummary:
```

- If either `whole_prompt` or `episode_prompt` is meaningful, use
  `transcript.speaker_labeled_text_timestamped()` and wrap the user prompt with
  `prompts.with_guidance(...)`. Otherwise use `transcript.speaker_labeled_text`
  and the bare prompt (today's behavior).

`synthesize_arc` gains an optional `whole_prompt`:

```python
def synthesize_arc(summaries, llm, *, whole_prompt: str | None = None) -> ArcOutline:
```

- Wrap `ARC_USER` with `with_guidance(whole=whole_prompt)` when present.

### 5. Script writer — `src/repodify/script/writer.py`

`write_script` gains an optional `whole_prompt`:

```python
def write_script(arc, llm, target_minutes, wpm, host_count=1, cast=None,
                 *, whole_prompt: str | None = None) -> Script:
```

Apply `with_guidance(base_user, whole=whole_prompt)` to `base_user` **before** the
attempt loop, so guidance is present on the initial draft and every expansion
retry. The `SCRIPT_EXPAND` suffix continues to be appended after the guidance.

### 6. Pipeline nodes — `src/repodify/pipeline/nodes.py`

`options` is already on `PipelineState`, so each node reads the prompts from it:

- `summarize_node`: for each ordered episode, pass
  `whole_prompt=options.custom_prompt` and
  `episode_prompt=options.episode_prompts.get(e.guid)` into `summarize_episode`.
- `arc_node`: pass `whole_prompt=options.custom_prompt` into `synthesize_arc`.
- `script_node`: pass `whole_prompt=options.custom_prompt` into `write_script`.

Nodes pass raw option values; `clean_prompt` (called inside the chain/writer
functions) treats empty/whitespace as no guidance, and the timestamp-vs-plain
transcript choice keys off whether cleaned guidance survives.

### 7. API — `src/repodify/api/schemas.py` and `api/app.py`

`CreateJobRequest` gains:

```python
custom_prompt: str | None = None
episode_prompts: dict[str, str] = {}
```

`create_job` passes both through into `JobOptions`. Length validation lives on
`JobOptions` (single source of truth); the request model stays a thin DTO. An
over-long prompt surfaces as a 422 from pydantic validation.

No new endpoints. `submit_voices` already reconstructs `JobOptions` from
`options_json` via `model_validate_json` and copies over specific fields; the new
fields ride along untouched through that path.

### 8. Web UI

**`web/src/api/types.ts`** — extend `CreateJobRequest`:

```ts
custom_prompt?: string | null
episode_prompts?: Record<string, string>
```

**`web/src/components/EpisodePicker.tsx`** — each episode row gets an inline
"▸ add note" / "▾ note" toggle that reveals a native `<textarea>`. The picker
takes two new props: `prompts: Record<string, string>` and
`onPromptChange(guid, value)`. Toggling open/closed is local component state; the
text value is lifted to `NewDigest`. Only selected episodes show the note control
(a note on an unselected episode has no effect).

**`web/src/routes/NewDigest.tsx`**:
- New state: `customPrompt: string`, `episodePrompts: Record<string, string>`.
- A **"Custom instructions"** native `<textarea>` in the format card, under
  Target length / Hosts, with helper text: steer emphasis, keep/skip sections, or
  reference times like `4:20`.
- On submit, include `custom_prompt` (omit/empty-string when blank) and
  `episode_prompts` filtered to selected episodes with non-empty text.

Keep all controls native `<textarea>`/`<input>` — the dashboard tests assert on
native form elements.

## Testing

**Python (pytest):**
- `prompts.with_guidance`: no guidance → returns base unchanged; whole only;
  episode only; both — asserts the guidance section is present and labeled.
- `Transcript.speaker_labeled_text_timestamped`: `[MM:SS]` prefixes; minutes >59
  formatting; unlabeled-speaker transcript still timestamped; grouping matches
  `speaker_labeled_text`'s grouping.
- `summarize_episode`: with a fake `StructuredLLM` capturing `(system, user)` —
  (a) no prompts → user equals today's bare prompt and uses untimestamped text;
  (b) with prompts → user contains the guidance block and the transcript portion
  is timestamped.
- `synthesize_arc` / `write_script`: guidance appears in the prompt when supplied;
  `write_script` still respects the word budget with guidance present.
- `JobOptions` validation: over-long `custom_prompt` and over-long
  `episode_prompts` value raise; whitespace-only values are dropped.
- Pipeline: a job carrying `custom_prompt` + `episode_prompts` reaches the LLM
  (assert via fake LLM capture); a job with none reproduces today's exact prompt
  (regression guard).

**Web (vitest):**
- `NewDigest` submits `custom_prompt` and `episode_prompts` (selected + non-empty
  only) in the create-job body.
- `EpisodePicker` note toggle reveals the textarea and calls `onPromptChange`.

## Backward compatibility

- New `JobOptions` / `CreateJobRequest` fields are optional with defaults; old
  persisted `options_json` blobs and existing API clients keep working.
- The default (no-prompt) summarizer input and prompts are unchanged, so existing
  pipeline snapshots/behavior hold.
</content>
</invoke>
