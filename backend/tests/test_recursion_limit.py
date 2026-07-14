"""
Regression test for LangGraph's recursion_limit.

LangGraph's default recursion_limit is 25 super-steps, counting every node
execution — not sections. Each section can take up to
retrieve_context + (draft_section + evaluate_section) per attempt (1 initial
+ N retries) + advance_section. With the default max_retries_per_section (3),
that's up to 10 steps per section, so even a handful of sections that need
full retries exceeds the default limit — proven live: a real 12-section run
hit "Recursion limit of 25 reached without hitting a stop condition".

api/main.py now passes an explicit, generously-sized recursion_limit (see
GENERATION_RECURSION_LIMIT) computed from the same constants PLANNING_PROMPT
enforces, instead of relying on LangGraph's default.
"""

import json

import pytest
from langgraph.errors import GraphRecursionError

from graph.builder import generation_graph
from graph.state import GenerationState


def _mock_toc(n_sections: int):
    return json.dumps([
        {"section_id": str(i + 1), "title": f"Section {i + 1}", "description": "d", "target_artifact_filter": "ALL"}
        for i in range(n_sections)
    ])


def _install_always_failing_critic(monkeypatch, n_sections: int):
    """Forces every section through the maximum number of draft/critique
    retries — the worst-case step count the recursion limit must absorb."""
    from graph import nodes

    call_count = {"n": 0}

    def fake_llm(prompt, max_tokens=4096):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _mock_toc(n_sections)
        if "passed" in prompt.lower() or "score" in prompt.lower() or "1-10" in prompt:
            return json.dumps({"passed": False, "issues": ["never good enough"], "improvement_instructions": "redo it", "score": 2})
        return "Drafted content."

    monkeypatch.setattr(nodes, "_llm", fake_llm)
    monkeypatch.setattr(nodes._vector_store, "retrieve_context", lambda **kw: "")


def test_default_recursion_limit_is_too_low_for_a_few_sections_with_retries(monkeypatch):
    """Control case: proves the bug is real, reproducible at small scale, and
    not specific to a large TOC — 3 sections forced through max retries alone
    exceeds LangGraph's default 25-step limit."""
    _install_always_failing_critic(monkeypatch, n_sections=3)

    with pytest.raises(GraphRecursionError):
        list(generation_graph.stream(
            GenerationState.initial("BRD"),
            stream_mode="values",
            config={"recursion_limit": 25},
        ))


def test_generation_recursion_limit_absorbs_worst_case_toc_and_retries(monkeypatch):
    """The fixed, generously-sized recursion_limit must get a full run to
    completion under the same worst-case retry pattern that broke the
    default limit above."""
    from api.main import GENERATION_RECURSION_LIMIT

    _install_always_failing_critic(monkeypatch, n_sections=3)

    final_state = None
    for state in generation_graph.stream(
        GenerationState.initial("BRD"),
        stream_mode="values",
        config={"recursion_limit": GENERATION_RECURSION_LIMIT},
    ):
        final_state = state

    assert final_state["status"] == "done"
    assert final_state["final_document"]
