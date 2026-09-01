from pathlib import Path

import respx

from repodify.transcribe.pyannote_cloud import PyannoteCloudDiarizer

BASE = "https://api.pyannote.ai/v1"


def test_diarize_uploads_polls_and_maps_turns(tmp_path: Path):
    audio = tmp_path / "ep.wav"
    audio.write_bytes(b"RIFF")
    dia = PyannoteCloudDiarizer(api_key="tok", poll_interval=0.0)
    with respx.mock:
        respx.post(f"{BASE}/media/input").respond(
            json={"url": "https://upload.example/put"}
        )
        respx.put("https://upload.example/put").respond(status_code=200)
        respx.post(f"{BASE}/diarize").respond(json={"jobId": "job-1", "status": "created"})
        respx.get(f"{BASE}/jobs/job-1").respond(
            json={
                "jobId": "job-1",
                "status": "succeeded",
                "output": {
                    "diarization": [
                        {"start": 0.0, "end": 1.5, "speaker": "SPEAKER_00"},
                        {"start": 1.5, "end": 3.0, "speaker": "SPEAKER_01"},
                    ]
                },
            }
        )
        result = dia.diarize(audio)
    assert [t.speaker for t in result.turns] == ["SPEAKER_00", "SPEAKER_01"]
    assert result.embeddings == {}
