"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from podcast_compactor.persistence.engine import init_db, make_engine, session_factory
from podcast_compactor.persistence.repo import JobRepository


@pytest.fixture
def sample_feed_xml() -> bytes:
    """Raw bytes of the sample RSS feed fixture."""
    return (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_bytes()


@pytest.fixture
def repo(tmp_path) -> JobRepository:
    """A JobRepository backed by a throwaway SQLite database."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return JobRepository(session_factory(engine))
