from pathlib import Path

from repodify.storage.base import Storage
from repodify.storage.filesystem import FilesystemStorage


def test_put_and_get_bytes_roundtrip(tmp_path):
    store = FilesystemStorage(tmp_path)
    uri = store.put_bytes("a/b/data.bin", b"hello")
    assert uri.startswith("file://")
    assert store.get_bytes("a/b/data.bin") == b"hello"
    assert store.exists("a/b/data.bin")


def test_put_file_copies(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("payload")
    store = FilesystemStorage(tmp_path / "store")
    store.put_file("nested/out.txt", src)
    assert store.get_bytes("nested/out.txt") == b"payload"


def test_missing_key_not_exists(tmp_path):
    store = FilesystemStorage(tmp_path)
    assert not store.exists("nope")
    assert store.local_path("nope") == (tmp_path / "nope")


def test_satisfies_storage_protocol(tmp_path):
    store = FilesystemStorage(tmp_path)
    assert isinstance(store, Storage)


def test_local_path_is_absolute_for_relative_root(tmp_path, monkeypatch):
    # Regression: with a relative root (e.g. DATA_DIR=data) local_path(...) must
    # still be absolute so callers can call `.as_uri()` — which raises on
    # relative paths and previously failed artifact recording in the pipeline.
    monkeypatch.chdir(tmp_path)
    store = FilesystemStorage(Path("data"))
    path = store.local_path("job/output/digest.wav")
    assert path.is_absolute()
    assert path.as_uri().startswith("file://")
