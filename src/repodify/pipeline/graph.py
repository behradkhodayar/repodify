"""Compile the pipeline nodes into a runnable LangGraph.

The graph is linear. Gated nodes (`transcribe`, `diarize`, `voices`,
`summarize`, `synth`) call `interrupt()` so the worker can persist a SQLite
checkpoint and wait for the user's local/BYOK config. `synth` also runs assemble.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from repodify.pipeline.nodes import make_nodes
from repodify.pipeline.state import Deps, PipelineState

_ORDER = [
    "resolve",
    "download",
    "transcribe",
    "diarize",
    "voices",
    "summarize",
    "arc",
    "script",
    "synth",
]


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
    """Build and compile the pipeline graph.

    `checkpointer` defaults to an in-memory saver (used in in-process tests); the
    worker supplies a SQLite saver so gates survive process restart.
    """
    return _compile(deps, _ORDER, checkpointer)
