"""
Regression tests for the generation graph's state-passing semantics.

`graph/builder.py` used to compile `StateGraph(dict)` — a plain, un-annotated
dict schema. LangGraph treats that as a single opaque channel and REPLACES the
entire state with whatever a node returns, silently dropping every key the
node didn't re-include (proven by the `test_state_replaced_wholesale_with_plain_dict_schema`
control case below). Since every node in graph/nodes.py returns only a partial
update, this meant no run could ever complete past the first node.

The fix: use graph.state.GenerationStateSchema (a TypedDict) as the schema, so
LangGraph creates one merge-safe channel per field.
"""

import json

from langgraph.graph import StateGraph, END

from graph.builder import generation_graph
from graph.state import GenerationState


def test_state_replaced_wholesale_with_plain_dict_schema():
    """Control case: demonstrates the bug this suite guards against."""
    def node_a(state):
        return {"a": 1}

    def node_b(state):
        return {"seen": dict(state), "b": 2}

    g = StateGraph(dict)
    g.add_node("node_a", node_a)
    g.add_node("node_b", node_b)
    g.set_entry_point("node_a")
    g.add_edge("node_a", "node_b")
    g.add_edge("node_b", END)

    result = g.compile().invoke({"x": "initial", "a": "stale"})
    # node_b never saw "x" — it was wiped out by node_a's partial return.
    assert "x" not in result["seen"]


def test_generation_graph_completes_full_happy_path(monkeypatch):
    """The actual compiled graph must carry artifact_type/toc/etc. through
    every node instead of losing them after the first partial return."""
    from graph import nodes

    call_count = {"n": 0}

    def fake_llm(prompt, max_tokens=4096):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return json.dumps([
                {"section_id": "1", "title": "Intro", "description": "d", "target_artifact_filter": "ALL"}
            ])
        if call_count["n"] == 2:
            return "Some drafted content."
        return json.dumps({"passed": True, "issues": [], "improvement_instructions": "", "score": 9})

    monkeypatch.setattr(nodes, "_llm", fake_llm)
    monkeypatch.setattr(nodes._vector_store, "retrieve_context", lambda **kw: "")

    final_state = generation_graph.invoke(GenerationState.initial("BRD"))

    assert final_state["status"] == "done"
    assert "Some drafted content." in final_state["final_document"]


def test_generation_graph_ends_cleanly_on_malformed_toc(monkeypatch):
    """A truncated/malformed TOC from the LLM must not crash downstream nodes —
    it should route straight to a clean error state instead."""
    from graph import nodes

    monkeypatch.setattr(
        nodes, "_llm",
        lambda prompt, max_tokens=4096: '[{"section_id": "1", "title": "Executive Summary", "description": "trunc',
    )

    final_state = generation_graph.invoke(GenerationState.initial("BRD"))

    assert final_state["status"] == "error"
    assert "TOC parsing failed" in final_state["error"]
