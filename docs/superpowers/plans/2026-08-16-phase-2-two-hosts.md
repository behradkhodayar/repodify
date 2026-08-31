# Phase 2 Two-Host Dialogue Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Extend the digest pipeline to optionally produce a two-host dialogue (`host_count=2`) rendered in two distinct stock voices, alongside the existing single-narrator mode.

**Architecture:** The change is contained. A new dialogue prompt drives Claude to write an alternating `host_a`/`host_b` conversation; `write_script` gains a two-host branch; the composition root supplies two stock voices. Synthesis and assembly already map `segment.speaker → voice`, so they are unchanged.

**Tech Stack:** Unchanged from Phase 1.

## Global Constraints

- English-only; word budget `words = target_minutes * wpm`.
- Two-host speaker labels are exactly `host_a` and `host_b`.
- No changes to the STT, storage, persistence, API, or assembly layers except where noted.
- TDD: failing test first, minimal impl, commit per task. Imperative commit messages, no emojis, no Claude co-authorship.
- Heavy ML deps stay lazy; default tests run on CPU in fake mode.

---

## Task 1: Dialogue prompt + two-host script writer

**Files:**
- Modify: `src/repodify/summarize/prompts.py` (add `SCRIPT_DIALOGUE_SYSTEM`, `SCRIPT_DIALOGUE_USER`)
- Modify: `src/repodify/script/writer.py`
- Modify: `tests/unit/script/test_writer.py`

**Interfaces:**
- Add module constant `HOST_SPEAKERS = ("host_a", "host_b")`.
- `write_script(arc, llm, target_minutes, wpm, host_count=1) -> Script`:
  - `host_count == 1`: unchanged (single narrator, speakers normalized to `narrator`).
  - `host_count == 2`: use the dialogue prompt; validate every `segment.speaker in HOST_SPEAKERS`; require ≥2 segments and that **both** hosts appear; raise `ValueError` otherwise.
  - `host_count` not in {1, 2}: `NotImplementedError`.

- [ ] **Step 1: Write failing tests**

```python
def test_write_script_two_hosts_uses_dialogue_and_keeps_speakers():
    returned = Script(segments=[
        ScriptSegment(speaker="host_a", text="one two three"),
        ScriptSegment(speaker="host_b", text="four five six"),
    ])
    llm = FakeStructuredLLM([returned])
    script = write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)
    assert {s.speaker for s in script.segments} == {"host_a", "host_b"}
    _system, user, schema = llm.calls[0]
    assert schema is Script
    assert "host_a" in user and "host_b" in user
    assert "3900" in user

def test_write_script_two_hosts_rejects_bad_speaker():
    llm = FakeStructuredLLM([Script(segments=[
        ScriptSegment(speaker="narrator", text="hi there friend"),
        ScriptSegment(speaker="host_b", text="hello back to you"),
    ])])
    with pytest.raises(ValueError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=2)

def test_write_script_rejects_three_hosts():
    llm = FakeStructuredLLM([Script(segments=[ScriptSegment(speaker="host_a", text="hi")])])
    with pytest.raises(NotImplementedError):
        write_script(_arc(), llm, target_minutes=30, wpm=130, host_count=3)
```

- [ ] **Step 2: Run — FAIL** (`test_write_script_rejects_multi_host_in_phase_1` will also need updating: change it to expect the three-host `NotImplementedError` or remove it, since `host_count=2` is now supported).
- [ ] **Step 3: Implement** the dialogue prompts and the two-host branch.
- [ ] **Step 4: Run — PASS** `pytest tests/unit/script/ -v`.
- [ ] **Step 5: Commit** `Add two-host dialogue script writer`.

---

## Task 2: Stock host voices in config + composition root

**Files:**
- Modify: `src/repodify/config.py` (add `host_a_ref_audio/text`, `host_b_ref_audio/text`)
- Modify: `src/repodify/worker/main.py` (`build_deps` voices)
- Modify: `src/repodify/ports/llm.py` (`LocalStubLLM` Script branch → alternating hosts)
- Modify: `.env.example`
- Modify: `tests/unit/worker/test_compose.py`

**Interfaces:**
- `Settings` gains `host_a_ref_audio: Path | None`, `host_a_ref_text: str | None`, `host_b_ref_audio: Path | None`, `host_b_ref_text: str | None`.
- `build_deps` `voices` dict includes `narrator`, `host_a`, `host_b` in both fake and real modes (real mode wires the respective ref clips).
- `LocalStubLLM.generate(..., Script)` returns a two-segment `host_a`/`host_b` script (single-host mode normalizes these to `narrator`, so both modes stay valid).

- [ ] **Step 1: Write failing test** — `build_deps(Settings(use_fakes=True, ...)).voices` contains `host_a` and `host_b`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** config fields, voices wiring, stub update, `.env.example` docs.
- [ ] **Step 4: Run — PASS** `pytest tests/unit/worker/ -v`.
- [ ] **Step 5: Commit** `Wire two stock host voices into the composition root`.

---

## Task 3: Two-host end-to-end integration test

**Files:**
- Create: `tests/integration/test_two_host_pipeline.py`

**Interfaces:** none new — exercises `run_pipeline` with `JobOptions(host_count=2)`.

- [ ] **Step 1: Write failing test** — run `run_pipeline` in fake mode (network mocked, `host_count=2`); assert job completes, a valid WAV is produced, and the script/segments used both `host_a` and `host_b` (assert via stored show notes / artifacts and that synthesis covered two speakers).
- [ ] **Step 2: Run — FAIL** (until Tasks 1–2 land; if run last, should PASS).
- [ ] **Step 3: Implement** the test; fix any wiring gaps.
- [ ] **Step 4: Run — PASS** `pytest tests/integration/ -v`.
- [ ] **Step 5: Commit** `Add two-host end-to-end integration test`.

---

## Task 4: Docs

**Files:**
- Modify: `README.md` (note `host_count` option and the two-host mode)

- [ ] **Step 1: Update** README run section to show creating a job with `"host_count": 2`.
- [ ] **Step 2: Commit** `Document two-host mode`.

---

## Self-Review

**Spec coverage:** Phase 2 = "2-host dialogue script + two distinct stock voices." Task 1 (dialogue script), Task 2 (two voices), Task 3 (verification), Task 4 (docs). ✔

**Placeholder scan:** none.

**Type consistency:** `HOST_SPEAKERS` used in `writer.py` and referenced by tests; `write_script` signature unchanged (only the `host_count=2` branch added); `voices` dict keys (`host_a`/`host_b`) match `LocalStubLLM` output speakers and the dialogue prompt labels.

**Deferred:** distinct host *display names* in spoken text, per-host voice cloning (Phase 3).
