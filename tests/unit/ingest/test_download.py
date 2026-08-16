import httpx
import pytest
import respx

from podcast_compactor.ingest.download import DownloadError, download_episode
from podcast_compactor.models.domain import Episode
from podcast_compactor.storage.filesystem import FilesystemStorage


def _episode() -> Episode:
    return Episode(
        guid="ep-1",
        title="Episode 1",
        audio_url="https://cdn.example.com/ep1.mp3",
        order_index=0,
    )


def test_download_streams_to_storage(tmp_path):
    store = FilesystemStorage(tmp_path)
    with respx.mock:
        respx.get("https://cdn.example.com/ep1.mp3").respond(content=b"AUDIOBYTES")
        with httpx.Client() as http:
            uri = download_episode(_episode(), store, http, "job1")
    assert uri.startswith("file://")
    assert store.get_bytes("job1/audio/0.mp3") == b"AUDIOBYTES"


def test_download_non_200_raises(tmp_path):
    store = FilesystemStorage(tmp_path)
    with respx.mock:
        respx.get("https://cdn.example.com/ep1.mp3").respond(status_code=404)
        with httpx.Client() as http:
            with pytest.raises(DownloadError):
                download_episode(_episode(), store, http, "job1")
