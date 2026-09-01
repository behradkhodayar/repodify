"""Pipeline node functions, built as closures over a `Deps` container.

Each node wraps its work in `repo.start_stage` / `finish_stage` so progress is
observable. Per-episode download/transcribe failures are recorded to the job
report and skipped; a stage only fails if *every* episode fails.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from langgraph.types import interrupt

from repodify.ingest.cache import JsonCache
from repodify.ingest.download import DownloadError, audio_key, download_episode
from repodify.ingest.feed import parse_feed
from repodify.ingest.fetch import fetch_feed
from repodify.models.domain import Transcript
from repodify.models.enums import StageName, StageState
from repodify.pipeline.progress import (
    DetailThrottler,
    format_bytes,
    format_percent,
    join_detail,
    model_id,
)
from repodify.pipeline.state import Deps, PipelineState
from repodify.script.writer import write_script
from repodify.summarize.chains import summarize_episode, synthesize_arc
from repodify.synth.assemble import (
    assemble_wav,
    build_show_notes,
    disclaimer_segment,
    synthesize_script,
    wav_duration_seconds,
)
from repodify.synth.gender import estimate_cast_registers
from repodify.synth.stock_voices import (
    effective_stock_catalog,
    interleave_by_register,
    match_by_gender,
    stock_voice,
)
from repodify.synth.voice_assignment import MAX_CAST, resolve_voice_assignments
from repodify.transcribe.diarization import (
    assign_speakers,
    roster_from_turns,
    unify_speakers_across_episodes,
)

logger = logging.getLogger(__name__)

NodeFn = Callable[[PipelineState], dict]


def _report(state: PipelineState) -> dict:
    report = dict(state.get("report") or {})
    report.setdefault("warnings", [])
    report.setdefault("skipped", [])
    return report


def _wants_speaker_id(options) -> bool:
    """Whether the job needs speaker-labeled transcripts (diarization).

    Opt-in cloning, the speaker-preserving digest, and the interactive voice review
    all need to know who said what; a plain single-narrator/two-host run does not.
    """
    assign = getattr(options, "assign_voices", False)
    return bool(options.clone or options.preserve_speakers or options.review_voices or assign)


def _take_gate(name: str, extra: dict | None = None) -> dict:
    """Pause the graph until the user submits this gate's local/BYOK config."""
    payload: dict = {"gate": name}
    if extra:
        payload.update(extra)
    value = interrupt(payload)
    return value if isinstance(value, dict) else {}


def _prepend_disclaimer(script, text: str):
    """Prepend a spoken AI disclaimer segment to a cloned-output script."""
    return script.model_copy(update={"segments": [disclaimer_segment(text), *script.segments]})


def make_nodes(deps: Deps) -> dict[str, NodeFn]:
    repo = deps.repo

    def resolve_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        repo.start_stage(job_id, StageName.RESOLVE, detail="fetching feed")
        try:
            feed_url = state["feed_url"]
            rss_url = deps.resolver_resolve(feed_url, deps.http)
            fetched = fetch_feed(
                rss_url, deps.http, cache=JsonCache(deps.settings.data_dir / "cache")
            )
            feed = parse_feed(feed_url, fetched.url, fetched.body)

            wanted = set(state["options"].episode_ids)
            selected = [e for e in feed.episodes if e.guid in wanted]
            if not selected:
                raise ValueError("no selected episodes matched the feed")

            repo.finish_stage(
                job_id,
                StageName.RESOLVE,
                StageState.DONE,
                detail=f"{len(selected)} episodes selected",
            )
            return {"feed": feed, "selected": selected}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.RESOLVE, StageState.FAILED, detail=str(exc))
            raise

    def download_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        selected = state["selected"]
        report = _report(state)

        # --- DOWNLOAD ---
        n_selected = len(selected)
        repo.start_stage(job_id, StageName.DOWNLOAD, detail=join_detail(f"0/{n_selected}"))
        throttler = DetailThrottler(
            lambda d: repo.update_stage_detail(job_id, StageName.DOWNLOAD, d)
        )
        downloaded = []
        total_bytes = 0
        for i, ep in enumerate(selected, start=1):
            last_done = 0

            def _bytes(done: int, total: int | None, i=i, ep=ep) -> None:
                nonlocal last_done
                last_done = done
                pct_s = format_percent(done, total) if total else None
                pct_f = (100.0 * done / total) if total else None
                size = (
                    f"{format_bytes(done)} / {format_bytes(total)}" if total else format_bytes(done)
                )
                throttler.update(
                    join_detail(ep.title, f"{i}/{n_selected}", pct_s, size),
                    pct=pct_f,
                )

            try:
                download_episode(ep, deps.storage, deps.http, job_id, on_progress=_bytes)
                total_bytes += last_done
                repo.add_artifact(
                    job_id,
                    "audio_download",
                    deps.storage.local_path(audio_key(job_id, ep)).as_uri(),
                    episode_guid=ep.guid,
                )
                downloaded.append(ep)
                throttler.flush(join_detail(ep.title, f"{i}/{n_selected}"))
            except Exception as exc:  # noqa: BLE001 - record and skip
                report["skipped"].append(f"download {ep.guid}: {exc}")
        if not downloaded:
            repo.finish_stage(job_id, StageName.DOWNLOAD, StageState.FAILED)
            repo.set_report(job_id, report)
            raise DownloadError("all selected episodes failed to download")
        repo.finish_stage(
            job_id,
            StageName.DOWNLOAD,
            StageState.DONE,
            detail=join_detail(
                f"{len(downloaded)}/{n_selected} downloaded",
                format_bytes(total_bytes) if total_bytes else None,
            ),
        )
        repo.set_report(job_id, report)
        return {"downloaded": downloaded, "report": report}

    def transcribe_node(state: PipelineState) -> dict:
        _take_gate("transcribe")
        job_id = state["job_id"]
        downloaded = list(state.get("downloaded") or state.get("selected") or [])
        report = _report(state)

        whisper = model_id(deps.transcriber)
        whisper_label = f"whisper {whisper}" if whisper else None
        n_dl = len(downloaded)
        repo.start_stage(
            job_id, StageName.TRANSCRIBE, detail=join_detail(f"0/{n_dl}", whisper_label)
        )
        transcripts: dict = {}
        try:
            for i, ep in enumerate(downloaded, start=1):
                repo.update_stage_detail(
                    job_id,
                    StageName.TRANSCRIBE,
                    join_detail(ep.title, f"{i}/{n_dl}", whisper_label),
                )
                try:
                    path: Path = deps.storage.local_path(audio_key(job_id, ep))
                    transcript = deps.transcriber.transcribe(path)
                    transcripts[ep.guid] = transcript.model_copy(update={"episode_guid": ep.guid})
                except Exception as exc:  # noqa: BLE001 - record and skip
                    report["skipped"].append(f"transcribe {ep.guid}: {exc}")
            if not transcripts:
                repo.finish_stage(job_id, StageName.TRANSCRIBE, StageState.FAILED)
                repo.set_report(job_id, report)
                raise RuntimeError("all episodes failed to transcribe")
            repo.finish_stage(
                job_id,
                StageName.TRANSCRIBE,
                StageState.DONE,
                detail=join_detail(f"{len(transcripts)} transcribed", whisper_label),
            )
        finally:
            # Free whisper's VRAM before diarization and the LLM/TTS stages; it
            # reloads lazily if the clone path needs it again.
            deps.transcriber.release()

        repo.set_report(job_id, report)
        return {"transcripts": transcripts, "report": report}

    def diarize_node(state: PipelineState) -> dict:
        choice = _take_gate("diarize")
        job_id = state["job_id"]
        options = state["options"]
        transcripts = dict(state.get("transcripts") or {})
        downloaded = list(state.get("downloaded") or state.get("selected") or [])
        report = _report(state)

        assign = choice.get("assign_voices")
        wants = True if assign is True else False if assign is False else _wants_speaker_id(options)

        dia = model_id(deps.diarizer)
        repo.start_stage(job_id, StageName.DIARIZE, detail=join_detail(dia) or None)
        cast: list = []
        if wants:
            try:
                results = {}
                to_diarize = [ep for ep in downloaded if ep.guid in transcripts]
                for i, ep in enumerate(to_diarize, start=1):
                    repo.update_stage_detail(
                        job_id,
                        StageName.DIARIZE,
                        join_detail(ep.title, f"{i}/{len(to_diarize)}", dia),
                    )
                    path = deps.storage.local_path(audio_key(job_id, ep))
                    results[ep.guid] = deps.diarizer.diarize(path)

                relabeled, pooled_roster = unify_speakers_across_episodes(
                    results, deps.settings.cross_episode_speaker_threshold
                )
                for guid, gturns in relabeled.items():
                    transcripts[guid] = transcripts[guid].model_copy(
                        update={
                            "segments": assign_speakers(transcripts[guid].segments, gturns),
                            "speakers": roster_from_turns(gturns),
                        }
                    )
                cast = pooled_roster[:MAX_CAST]
                speaker_ids = {s.id for t in transcripts.values() for s in t.speakers}
                repo.finish_stage(
                    job_id,
                    StageName.DIARIZE,
                    StageState.DONE,
                    detail=join_detail(
                        f"{len(cast)} cast / {len(speaker_ids)} global speakers", dia
                    ),
                )
            except Exception as exc:
                repo.finish_stage(job_id, StageName.DIARIZE, StageState.FAILED, detail=str(exc))
                raise
            finally:
                deps.diarizer.release()
        else:
            repo.finish_stage(
                job_id, StageName.DIARIZE, StageState.SKIPPED, detail="no voice feature requested"
            )

        repo.set_report(job_id, report)
        updates: dict = {"transcripts": transcripts, "report": report, "cast": cast}
        if assign is True:
            updates["options"] = options.model_copy(
                update={"preserve_speakers": True, "review_voices": True}
            )
        return updates

    def voices_node(state: PipelineState) -> dict:
        options = state["options"]
        if not _wants_speaker_id(options):
            return {}
        speakers = [
            {
                "speaker_id": s.id,
                "speaking_seconds": s.speaking_seconds,
                "display_name": s.label,
            }
            for s in (state.get("cast") or [])
        ]
        _take_gate("voices", {"speakers": speakers})
        report = _report(state)
        report["speakers"] = speakers
        deps.repo.set_report(state["job_id"], report)
        return {"report": report}

    def summarize_node(state: PipelineState) -> dict:
        _take_gate("summarize")
        job_id = state["job_id"]
        llm = model_id(deps.llm_map)
        transcripts = state["transcripts"]
        # Summarize in chronological order, only episodes we transcribed.
        ordered = [e for e in state["selected"] if e.guid in transcripts]
        repo.start_stage(job_id, StageName.SUMMARIZE, detail=join_detail(f"0/{len(ordered)}", llm))
        try:
            summaries = []
            for i, e in enumerate(ordered, start=1):
                repo.update_stage_detail(
                    job_id,
                    StageName.SUMMARIZE,
                    join_detail(e.title, f"{i}/{len(ordered)}", llm),
                )
                summaries.append(
                    summarize_episode(
                        transcripts[e.guid],
                        e.title,
                        e.order_index,
                        deps.llm_map,
                        whole_prompt=state["options"].custom_prompt,
                        episode_prompt=state["options"].episode_prompts.get(e.guid),
                    )
                )
            repo.finish_stage(
                job_id,
                StageName.SUMMARIZE,
                StageState.DONE,
                detail=join_detail(f"{len(summaries)} summaries", llm),
            )
            return {"summaries": summaries}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.SUMMARIZE, StageState.FAILED, detail=str(exc))
            raise

    def arc_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        llm = model_id(deps.llm_reduce)
        repo.start_stage(
            job_id, StageName.ARC, detail=join_detail("synthesizing through-line", llm)
        )
        try:
            arc = synthesize_arc(
                state["summaries"],
                deps.llm_reduce,
                whole_prompt=state["options"].custom_prompt,
            )
            repo.finish_stage(
                job_id,
                StageName.ARC,
                StageState.DONE,
                detail=join_detail(f"{len(arc.beats)} beats", llm),
            )
            return {"arc": arc}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.ARC, StageState.FAILED, detail=str(exc))
            raise

    def script_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        options = state["options"]
        llm = model_id(deps.llm_reduce)
        repo.start_stage(
            job_id,
            StageName.SCRIPT,
            detail=join_detail(f"writing {options.target_minutes} min script", llm),
        )
        try:
            # Cast is computed in the DIARIZE stage (and persisted across an
            # interactive review); the digest is speaker-preserving when it is set.
            cast = list(state.get("cast") or [])
            if options.preserve_speakers and not cast:
                raise ValueError("preserve_speakers: diarization found no speakers")
            script = write_script(
                state["arc"],
                deps.llm_reduce,
                target_minutes=options.target_minutes,
                wpm=deps.settings.wpm,
                host_count=options.host_count,
                cast=cast if options.preserve_speakers else None,
                whole_prompt=options.custom_prompt,
            )
            est = script.estimated_minutes(deps.settings.wpm)
            repo.finish_stage(
                job_id,
                StageName.SCRIPT,
                StageState.DONE,
                detail=join_detail(f"{script.word_count} words", f"~{est:.0f} min", llm),
            )
            return {"script": script, "cast": cast}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.SCRIPT, StageState.FAILED, detail=str(exc))
            raise

    def _episode_source(state: PipelineState, job_id: str):
        """The first transcribed episode's audio path + labeled transcript."""
        first = next(e for e in state["selected"] if e.guid in state["transcripts"])
        return (
            deps.storage.local_path(audio_key(job_id, first)),
            state["transcripts"][first.guid],
        )

    def _all_sources(state: PipelineState, job_id: str):
        """(audio path, labeled transcript) for every transcribed episode, in order."""
        return [
            (deps.storage.local_path(audio_key(job_id, e)), state["transcripts"][e.guid])
            for e in state["selected"]
            if e.guid in state["transcripts"]
        ]

    def _speaker_seconds(transcript: Transcript, speaker_id: str) -> float:
        return next((s.speaking_seconds for s in transcript.speakers if s.id == speaker_id), 0.0)

    def _record_ref_clip(job_id: str, key: str, voice) -> None:
        if voice.ref_audio_path is not None:
            repo.add_artifact(
                job_id, "reference_clip", voice.ref_audio_path.as_uri(), episode_guid=key
            )

    def synth_node(state: PipelineState) -> dict:
        _take_gate("tts")
        job_id = state["job_id"]
        script = state["script"]
        arc = state["arc"]
        options = state["options"]
        cloned_output = False  # drives the disclaimer / watermark / synthetic guardrails

        # --- TTS ---
        tts_label = model_id(deps.tts)
        repo.start_stage(job_id, StageName.TTS, detail=join_detail(tts_label) or None)
        try:
            if options.preserve_speakers:
                # Speaker-preserving digest: each cast speaker in their assigned
                # voice — their own clone or a stock catalog voice.
                cast_ids = [s.id for s in state["cast"]]
                # For stock voices (not cloning), match each speaker to a same-gender
                # catalog voice by default — inferred from their diarized pitch — so a
                # male host gets a male voice. Where pitch is unclear we fall back to
                # the register-interleaved catalog, which at least keeps voices
                # distinct; an explicit user assignment overrides both.
                preferred_stock: dict[str, str] = {}
                catalog = effective_stock_catalog(deps.stock_catalog)
                if not options.clone:
                    registers = estimate_cast_registers(_all_sources(state, job_id), cast_ids)
                    preferred_stock = match_by_gender(cast_ids, registers, catalog)
                assignments = resolve_voice_assignments(
                    cast_ids,
                    options,
                    interleave_by_register(catalog),
                    deps.settings.default_stock_voice,
                    preferred_stock=preferred_stock,
                )
                clone_ids = [i for i in cast_ids if assignments[i].mode == "clone"]
                voices = {}
                if clone_ids:
                    # Cut each speaker's reference clip from the episode where they
                    # talk most: a cross-episode identity may barely appear in (or be
                    # absent from) episode 1, so a fixed episode would clone the wrong
                    # voice or an empty clip.
                    sources = _all_sources(state, job_id)
                    by_source: dict[int, list[str]] = defaultdict(list)
                    for sid in clone_ids:
                        best = max(
                            range(len(sources)),
                            key=lambda i, s=sid: _speaker_seconds(sources[i][1], s),
                        )
                        by_source[best].append(sid)
                    for i, sids in by_source.items():
                        audio_path, transcript = sources[i]
                        cloned = deps.voice_cloner.clone(
                            audio_path, transcript, sids, deps.storage, job_id
                        )
                        for key, voice in cloned.items():
                            voices[key] = voice
                            _record_ref_clip(job_id, key, voice)
                for sid in cast_ids:
                    if assignments[sid].mode == "stock":
                        voices[sid] = stock_voice(assignments[sid].stock_voice)
                cloned_output = bool(clone_ids)
                if cloned_output:
                    script = _prepend_disclaimer(script, deps.settings.clone_disclaimer)
                    voices["disclaimer"] = stock_voice(deps.settings.default_stock_voice)
            elif options.clone:
                # Legacy opt-in cloning: map the script's roles (host_a/host_b or
                # narrator) onto the most-talkative detected speakers, clone those,
                # prepend a spoken disclaimer, and watermark the output.
                audio_path, transcript = _episode_source(state, job_id)
                roles = sorted({seg.speaker for seg in script.segments})
                ranked = [s.id for s in transcript.speakers]
                role_to_diar = dict(zip(roles, ranked, strict=False))
                cloned = deps.voice_cloner.clone(
                    audio_path, transcript, list(role_to_diar.values()), deps.storage, job_id
                )
                voices = {}
                for role, diar in role_to_diar.items():
                    if diar in cloned:
                        voices[role] = cloned[diar]
                        _record_ref_clip(job_id, role, cloned[diar])
                cloned_output = True
                script = _prepend_disclaimer(script, deps.settings.clone_disclaimer)
                voices["disclaimer"] = deps.voices["narrator"]
            else:
                voices = deps.voices

            def _tts_progress(i: int, n: int) -> None:
                repo.update_stage_detail(
                    job_id,
                    StageName.TTS,
                    join_detail(f"segment {i}/{n}", tts_label),
                )

            segments = synthesize_script(script, deps.tts, voices, on_progress=_tts_progress)
            repo.finish_stage(
                job_id,
                StageName.TTS,
                StageState.DONE,
                detail=join_detail(f"{len(segments)} segments", tts_label),
            )
        except Exception as exc:
            repo.finish_stage(job_id, StageName.TTS, StageState.FAILED, detail=str(exc))
            raise
        finally:
            # Free F5-TTS's VRAM once synthesis is done; assembly is CPU-only.
            deps.tts.release()

        # --- ASSEMBLE ---
        repo.start_stage(job_id, StageName.ASSEMBLE, detail="stitching WAV")
        try:
            wav = assemble_wav(segments)
            if cloned_output:
                wav = deps.watermarker.embed(wav)
            output_uri = deps.storage.put_bytes(f"{job_id}/output/digest.wav", wav)
            mp3_path = deps.storage.local_path(f"{job_id}/output/digest.mp3")
            repo.update_stage_detail(job_id, StageName.ASSEMBLE, "transcoding mp3")
            deps.transcoder.to_mp3(deps.storage.local_path(f"{job_id}/output/digest.wav"), mp3_path)
            notes = build_show_notes(
                arc,
                script,
                segments,
                synthetic=cloned_output,
                disclaimer=deps.settings.clone_disclaimer if cloned_output else None,
            )
            deps.storage.put_bytes(
                f"{job_id}/output/show_notes.json",
                notes.model_dump_json(indent=2).encode(),
            )
            deps.storage.put_bytes(
                f"{job_id}/output/script.json",
                script.model_dump_json(indent=2).encode(),
            )
            repo.add_artifact(job_id, "output_audio", output_uri)
            repo.add_artifact(job_id, "output_audio_mp3", mp3_path.as_uri())
            repo.add_artifact(
                job_id,
                "show_notes",
                deps.storage.local_path(f"{job_id}/output/show_notes.json").as_uri(),
            )
            repo.add_artifact(
                job_id,
                "script",
                deps.storage.local_path(f"{job_id}/output/script.json").as_uri(),
            )
            duration_s = wav_duration_seconds(wav)
            repo.finish_stage(
                job_id,
                StageName.ASSEMBLE,
                StageState.DONE,
                detail=join_detail(
                    "digest ready",
                    f"{duration_s:.0f}s" if duration_s else None,
                ),
            )
        except Exception as exc:
            repo.finish_stage(job_id, StageName.ASSEMBLE, StageState.FAILED, detail=str(exc))
            raise

        report = _report(state)
        report["show_notes"] = json.loads(notes.model_dump_json())
        repo.set_report(job_id, report)
        return {"output_uri": output_uri, "report": report}

    return {
        "resolve": resolve_node,
        "download": download_node,
        "transcribe": transcribe_node,
        "diarize": diarize_node,
        "voices": voices_node,
        "summarize": summarize_node,
        "arc": arc_node,
        "script": script_node,
        "synth": synth_node,
    }
