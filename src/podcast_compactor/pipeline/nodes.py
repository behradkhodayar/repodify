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

logger = logging.getLogger(__name__)

NodeFn = Callable[[PipelineState], dict]


def _report(state: PipelineState) -> dict:
    report = dict(state.get("report") or {})
    report.setdefault("warnings", [])
    report.setdefault("skipped", [])
    return report


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
            repo.set_report(job_id, report)
            return {"transcripts": transcripts, "report": report}
        finally:
            # Free whisper's VRAM before the LLM and TTS stages; it reloads
            # lazily if the clone path needs it again.
            deps.transcriber.release()

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
            script = write_script(
                state["arc"],
                deps.llm_reduce,
                target_minutes=options.target_minutes,
                wpm=deps.settings.wpm,
                host_count=options.host_count,
            )
            repo.finish_stage(job_id, StageName.SCRIPT, StageState.DONE,
                              detail=f"{script.word_count} words")
            return {"script": script}
        except Exception as exc:
            repo.finish_stage(job_id, StageName.SCRIPT, StageState.FAILED, detail=str(exc))
            raise

    def synth_node(state: PipelineState) -> dict:
        job_id = state["job_id"]
        script = state["script"]
        arc = state["arc"]
        options = state["options"]

        # --- TTS ---
        repo.start_stage(job_id, StageName.TTS)
        try:
            if options.clone:
                # Opt-in cloning: build cloned voices from the episode audio, prepend a
                # spoken disclaimer (in a non-cloned voice), and watermark the output.
                audio_paths = [
                    deps.storage.local_path(audio_key(job_id, ep))
                    for ep in state["selected"]
                    if ep.guid in state["transcripts"]
                ]
                content_speakers = sorted({seg.speaker for seg in script.segments})
                cloned = deps.voice_cloner.clone(
                    audio_paths, content_speakers, deps.storage, job_id
                )
                for key, voice in cloned.items():
                    if voice.ref_audio_path is not None:
                        repo.add_artifact(
                            job_id, "reference_clip", voice.ref_audio_path.as_uri(),
                            episode_guid=key,
                        )
                script = script.model_copy(
                    update={
                        "segments": [
                            disclaimer_segment(deps.settings.clone_disclaimer),
                            *script.segments,
                        ]
                    }
                )
                voices = {**cloned, "disclaimer": deps.voices["narrator"]}
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
            if options.clone:
                wav = deps.watermarker.embed(wav)
            output_uri = deps.storage.put_bytes(f"{job_id}/output/digest.wav", wav)
            notes = build_show_notes(
                arc, script, segments,
                synthetic=options.clone,
                disclaimer=deps.settings.clone_disclaimer if options.clone else None,
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
