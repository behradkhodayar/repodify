"""The worker imports pipeline nodes at boot. That path must not require numpy."""

from __future__ import annotations

import ast
from pathlib import Path

DIARIZATION = (
    Path(__file__).resolve().parents[3]
    / "src/repodify/transcribe/diarization.py"
)


def test_diarization_does_not_import_numpy_or_clustering_at_module_level():
    tree = ast.parse(DIARIZATION.read_text())
    top_level = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.extend(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.append(node.module)
    assert "numpy" not in top_level
    assert not any("speaker_clustering" in name for name in top_level)
