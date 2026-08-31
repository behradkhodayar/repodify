"""Compile the pipeline nodes into runnable LangGraphs.

`build_graph` is the whole pipeline (create → complete). The interactive
voice-review flow splits it in two around the diarization pause: `build_ingest_graph`
runs up to and including diarization, and `build_digest_graph` resumes from the
already-labeled transcripts once the user has assigned voices.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from repodify.pipeline.nodes import make_nodes
from repodify.pipeline.state import Deps, PipelineState

# Full linear stage order. `download` also runs transcribe + diarize; `synth` also
# runs assemble.
_ORDER = ["resolve", "download", "summarize", "arc", "script", "synth"]
# The interactive review pauses between these two segments.
_INGEST = ["resolve", "download"]
_DIGEST = ["summarize", "arc", "script", "synth"]


def _compile(deps: Deps, order: list[str], checkpointer):
    nodes = make_nodes(deps)
    graph = StateGraph(PipelineState)
    for name in order:
        graph.add_node(name, nodes[name])
    graph.add_edge(START, order[0])
    for src, dst in zip(order, order[1:], strict=False):
        graph.add_edge(src, dst)
    graph.add_edge(order[-1], END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


def build_graph(deps: Deps, checkpointer=None):
    """Build and compile the whole pipeline graph.

    `checkpointer` defaults to an in-memory saver (used in tests); the worker
    supplies a Postgres-backed saver in production.
    """
    return _compile(deps, _ORDER, checkpointer)


def build_ingest_graph(deps: Deps, checkpointer=None):
    """Resolve → download (transcribe + diarize). The half before the voice review."""
    return _compile(deps, _INGEST, checkpointer)


def build_digest_graph(deps: Deps, checkpointer=None):
    """Summarize → arc → script → synth. Resumes from labeled transcripts."""
    return _compile(deps, _DIGEST, checkpointer)
