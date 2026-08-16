from podcast_compactor.storage.base import Storage
from podcast_compactor.storage.filesystem import FilesystemStorage


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
