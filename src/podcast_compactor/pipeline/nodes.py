"""Pipeline node functions, built as closures over a `Deps` container.

Each node wraps its work in `repo.start_stage` / `finish_stage` so progress is
observable. Per-episode download/transcribe failures are recorded to the job
report and skipped; a stage only fails if *every* episode fails.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from podcast_compactor.ingest.download import DownloadError, audio_key, download_episode
from podcast_compactor.ingest.feed import parse_feed
from podcast_compactor.models.enums import StageName, StageState
from podcast_compactor.pipeline.state import Deps, PipelineState
from podcast_compactor.script.writer import write_script
from podcast_compactor.summarize.chains import summarize_episode, synthesize_arc
from podcast_compactor.synth.assemble import (
    assemble_wav,
    build_show_notes,
    disclaimer_segment,
    synthesize_script,
)
from podcast_compactor.synth.stock_voices import list_stock_voices, stock_voice
from podcast_compactor.synth.voice_assignment import resolve_voice_assignments, select_cast
from podcast_compactor.transcribe.diarization import assign_speakers, roster_from_turns

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
    return bool(options.clone or options.preserve_speakers or options.review_voices)


def _prepend_disclaimer(script, text: str):
    """Prepend a spoken AI disclaimer segment to a cloned-output script."""
    return script.model_copy(
        update={"segments": [disclaimer_segment(text), *script.segments]}
    )


def make_nodes(deps: Deps) -> dict[str, NodeFn]:
    repo = deps.repo

    def resolve_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        repo.start_stage(job_id, StageName.RESOLVE)
        try:
            feed_url = state["feed_url"]
            rss_url = deps.resolver_resolve(feed_url, deps.http)
            resp = deps.http.get(rss_url, follow_redirects=True)
            resp.raise_for_status()
            feed = parse_feed(feed_url, rss_url, resp.content)

            wanted = set(state["options"].episode_ids)
            selected = [e for e in feed.episodes if e.guid in wanted]
            if not selected:
                raise ValueError("no selected episodes matched the feed")

            repo.finish_stage(job_id, StageName.RESOLVE, StageState.DONE,
                              detail=f"{len(selected)} episodes selected")
            return {"feed": feed, "selected": selected}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.RESOLVE, StageState.FAILED, detail=str(exc))
            raise

    def download_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        selected = state["selected"]
        options = state["options"]
        report = _report(state)

        # --- DOWNLOAD ---
        repo.start_stage(job_id, StageName.DOWNLOAD)
        downloaded = []
        for ep in selected:
            try:
                download_episode(ep, deps.storage, deps.http, job_id)
                repo.add_artifact(
                    job_id, "audio_download",
                    deps.storage.local_path(audio_key(job_id, ep)).as_uri(),
                    episode_guid=ep.guid,
                )
                downloaded.append(ep)
            except Exception as exc:  # noqa: BLE001 - record and skip
                report["skipped"].append(f"download {ep.guid}: {exc}")
        if not downloaded:
            repo.finish_stage(job_id, StageName.DOWNLOAD, StageState.FAILED)
            repo.set_report(job_id, report)
            raise DownloadError("all selected episodes failed to download")
        repo.finish_stage(job_id, StageName.DOWNLOAD, StageState.DONE,
                          detail=f"{len(downloaded)}/{len(selected)} downloaded")

        # --- TRANSCRIBE ---
        repo.start_stage(job_id, StageName.TRANSCRIBE)
        transcripts: dict = {}
        try:
            for ep in downloaded:
                try:
                    path: Path = deps.storage.local_path(audio_key(job_id, ep))
                    transcript = deps.transcriber.transcribe(path)
                    transcripts[ep.guid] = transcript.model_copy(
                        update={"episode_guid": ep.guid}
                    )
                except Exception as exc:  # noqa: BLE001 - record and skip
                    report["skipped"].append(f"transcribe {ep.guid}: {exc}")
            if not transcripts:
                repo.finish_stage(job_id, StageName.TRANSCRIBE, StageState.FAILED)
                repo.set_report(job_id, report)
                raise RuntimeError("all episodes failed to transcribe")
            repo.finish_stage(job_id, StageName.TRANSCRIBE, StageState.DONE,
                              detail=f"{len(transcripts)} transcribed")
        finally:
            # Free whisper's VRAM before diarization and the LLM/TTS stages; it
            # reloads lazily if the clone path needs it again.
            deps.transcriber.release()

        # --- DIARIZE ---
        # Label each transcript segment with who spoke it, so later stages can
        # attribute content — and voices — to specific speakers. Only run when a
        # voice feature needs it; otherwise the stage is skipped (no GPU cost).
        repo.start_stage(job_id, StageName.DIARIZE)
        cast: list = []
        if _wants_speaker_id(options):
            try:
                for ep in downloaded:
                    if ep.guid not in transcripts:
                        continue
                    path = deps.storage.local_path(audio_key(job_id, ep))
                    turns = deps.diarizer.diarize(path)
                    transcripts[ep.guid] = transcripts[ep.guid].model_copy(
                        update={
                            "segments": assign_speakers(
                                transcripts[ep.guid].segments, turns
                            ),
                            "speakers": roster_from_turns(turns),
                        }
                    )
                # The digest cast (for the speaker-preserving / review flows) is the
                # first transcribed episode's roster, capped.
                first = next((e for e in downloaded if e.guid in transcripts), None)
                if first is not None:
                    cast = select_cast(transcripts[first.guid])
                speaker_ids = {s.id for t in transcripts.values() for s in t.speakers}
                repo.finish_stage(job_id, StageName.DIARIZE, StageState.DONE,
                                  detail=f"{len(speaker_ids)} speakers")
            except Exception as exc:
                repo.finish_stage(job_id, StageName.DIARIZE, StageState.FAILED,
                                  detail=str(exc))
                raise
            finally:
                # Free pyannote's VRAM before the LLM/TTS stages.
                deps.diarizer.release()
        else:
            repo.finish_stage(job_id, StageName.DIARIZE, StageState.SKIPPED,
                              detail="no voice feature requested")

        repo.set_report(job_id, report)
        return {"transcripts": transcripts, "report": report, "cast": cast}

    def summarize_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        repo.start_stage(job_id, StageName.SUMMARIZE)
        try:
            transcripts = state["transcripts"]
            # Summarize in chronological order, only episodes we transcribed.
            ordered = [e for e in state["selected"] if e.guid in transcripts]
            summaries = [
                summarize_episode(transcripts[e.guid], e.title, e.order_index, deps.llm_map)
                for e in ordered
            ]
            repo.finish_stage(job_id, StageName.SUMMARIZE, StageState.DONE,
                              detail=f"{len(summaries)} summaries")
            return {"summaries": summaries}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.SUMMARIZE, StageState.FAILED, detail=str(exc))
            raise

    def arc_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        repo.start_stage(job_id, StageName.ARC)
        try:
            arc = synthesize_arc(state["summaries"], deps.llm_reduce)
            repo.finish_stage(job_id, StageName.ARC, StageState.DONE)
            return {"arc": arc}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.ARC, StageState.FAILED, detail=str(exc))
            raise

    def script_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        options = state["options"]
        repo.start_stage(job_id, StageName.SCRIPT)
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
            )
            repo.finish_stage(job_id, StageName.SCRIPT, StageState.DONE,
                              detail=f"{script.word_count} words")
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

    def _record_ref_clip(job_id: str, key: str, voice) -> None:
        if voice.ref_audio_path is not None:
            repo.add_artifact(
                job_id, "reference_clip", voice.ref_audio_path.as_uri(), episode_guid=key
            )

    def synth_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        script = state["script"]
        arc = state["arc"]
        options = state["options"]
        cloned_output = False  # drives the disclaimer / watermark / synthetic guardrails

        # --- TTS ---
        repo.start_stage(job_id, StageName.TTS)
        try:
            if options.preserve_speakers:
                # Speaker-preserving digest: each cast speaker in their assigned
                # voice — their own clone or a stock catalog voice.
                cast_ids = [s.id for s in state["cast"]]
                assignments = resolve_voice_assignments(
                    cast_ids, options, list_stock_voices(), deps.settings.default_stock_voice
                )
                clone_ids = [i for i in cast_ids if assignments[i].mode == "clone"]
                voices = {}
                if clone_ids:
                    audio_path, transcript = _episode_source(state, job_id)
                    cloned = deps.voice_cloner.clone(
                        audio_path, transcript, clone_ids, deps.storage, job_id
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

            segments = synthesize_script(script, deps.tts, voices)
            repo.finish_stage(job_id, StageName.TTS, StageState.DONE,
                              detail=f"{len(segments)} segments")
        except Exception as exc:
            repo.finish_stage(job_id, StageName.TTS, StageState.FAILED, detail=str(exc))
            raise
        finally:
            # Free F5-TTS's VRAM once synthesis is done; assembly is CPU-only.
            deps.tts.release()

        # --- ASSEMBLE ---
        repo.start_stage(job_id, StageName.ASSEMBLE)
        try:
            wav = assemble_wav(segments)
            if cloned_output:
                wav = deps.watermarker.embed(wav)
            output_uri = deps.storage.put_bytes(f"{job_id}/output/digest.wav", wav)
            mp3_path = deps.storage.local_path(f"{job_id}/output/digest.mp3")
            deps.transcoder.to_mp3(
                deps.storage.local_path(f"{job_id}/output/digest.wav"), mp3_path
            )
            notes = build_show_notes(
                arc, script, segments,
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
                job_id, "show_notes",
                deps.storage.local_path(f"{job_id}/output/show_notes.json").as_uri(),
            )
            repo.add_artifact(
                job_id, "script",
                deps.storage.local_path(f"{job_id}/output/script.json").as_uri(),
            )
            repo.finish_stage(job_id, StageName.ASSEMBLE, StageState.DONE)
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
        "summarize": summarize_node,
        "arc": arc_node,
        "script": script_node,
        "synth": synth_node,
    }
