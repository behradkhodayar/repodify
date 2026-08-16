"""Compile the pipeline nodes into a runnable LangGraph."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from podcast_compactor.pipeline.nodes import make_nodes
from podcast_compactor.pipeline.state import Deps, PipelineState

# Linear stage order for the Phase 1 pipeline.
_ORDER = ["resolve", "download", "summarize", "arc", "script", "synth"]


def build_graph(deps: Deps, checkpointer=None):
    """Build and compile the pipeline graph.

    `checkpointer` defaults to an in-memory saver (used in tests); the worker
    supplies a Postgres-backed saver in production.
    """
    nodes = make_nodes(deps)
    graph = StateGraph(PipelineState)

    for name in _ORDER:
        graph.add_node(name, nodes[name])

    graph.add_edge(START, _ORDER[0])
    for src, dst in zip(_ORDER, _ORDER[1:], strict=False):
        graph.add_edge(src, dst)
    graph.add_edge(_ORDER[-1], END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())
