"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_feed_xml() -> bytes:
    """Raw bytes of the sample RSS feed fixture."""
    return (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_bytes()
