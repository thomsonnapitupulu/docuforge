"""
LangGraph Graph Builder for DocuForge.

Assembles the generation state machine:

  START
    │
    ▼
  plan_document
    │
    ├── [TOC parse failed] ──► END
    │
    ▼
  retrieve_context ◄──────────────────────┐
    │                                     │
    ▼                                     │
  draft_section ◄──────┐                 │
    │                  │                 │
    ▼                  │                 │
  evaluate_section     │                 │
    │                  │                 │
    ├── [fail+retries] ┘                 │
    │                                    │
    └── [pass/max_retry]                 │
          │                              │
          ▼                              │
        advance_section ─────────────────┘
          │
          └── [all done]
                │
                ▼
            compile_document
                │
                ▼
              END
"""

from langgraph.graph import StateGraph, END

from graph.nodes import (
    plan_document,
    retrieve_context,
    draft_section,
    evaluate_section,
    advance_section,
    compile_document,
    route_after_planning,
    route_after_evaluation,
    route_after_advance,
)
from graph.state import GenerationStateSchema


def build_generation_graph():
    """
    Compile and return the LangGraph StateGraph for document generation.
    Call .invoke(state) or .stream(state) on the returned graph.
    """

    builder = StateGraph(GenerationStateSchema)

    # ── Register nodes ───────────────────────────────────────────────────────
    builder.add_node("plan_document",    plan_document)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("draft_section",    draft_section)
    builder.add_node("evaluate_section", evaluate_section)
    builder.add_node("advance_section",  advance_section)
    builder.add_node("compile_document", compile_document)

    # ── Entry point ──────────────────────────────────────────────────────────
    builder.set_entry_point("plan_document")

    # ── Linear edges ─────────────────────────────────────────────────────────
    builder.add_edge("retrieve_context", "draft_section")
    builder.add_edge("draft_section",    "evaluate_section")

    # ── Conditional: Planning result → proceed OR stop on TOC parse failure ──
    builder.add_conditional_edges(
        "plan_document",
        route_after_planning,
        {
            "retrieve_context": "retrieve_context",
            "end": END,
        }
    )

    # ── Conditional: Critic result → redraft OR advance ──────────────────────
    builder.add_conditional_edges(
        "evaluate_section",
        route_after_evaluation,
        {
            "draft_section":  "draft_section",
            "advance_section": "advance_section",
        }
    )

    # ── Conditional: Advance → next section OR compile ───────────────────────
    builder.add_conditional_edges(
        "advance_section",
        route_after_advance,
        {
            "retrieve_context": "retrieve_context",
            "compile_document": "compile_document",
        }
    )

    # ── Terminal edge ─────────────────────────────────────────────────────────
    builder.add_edge("compile_document", END)

    return builder.compile()


# Singleton — compiled once at import
generation_graph = build_generation_graph()
