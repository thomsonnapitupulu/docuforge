"""
LangGraph State Schema for DocuForge.

The GenerationState is the single source of truth flowing through every node
in the generation graph. It accumulates sections, tracks retries, and
carries the final compiled document.
"""

from typing import Optional, TypedDict
from dataclasses import dataclass, field


@dataclass
class SectionPlan:
    """One entry from the TOC produced by the planning node."""
    section_id: str
    title: str
    description: str
    target_artifact_filter: str


@dataclass
class SectionDraft:
    """Tracks the draft lifecycle for a single section."""
    section_id: str
    title: str
    content: str = ""
    passed_critic: bool = False
    retry_count: int = 0
    critic_issues: list[str] = field(default_factory=list)
    improvement_instructions: str = ""
    retrieved_context: str = ""


class GenerationStateSchema(TypedDict, total=False):
    """
    LangGraph state schema. Passed to StateGraph(...) so each field becomes its
    own merge-safe channel — a node's return dict updates only the keys it
    includes, leaving the rest of the state untouched. (A plain, un-annotated
    `dict` schema does NOT do this: LangGraph treats it as a single opaque
    channel and replaces the *entire* state with whatever a node returns,
    silently dropping every key the node didn't re-include.)
    """
    artifact_type: str
    reference_summary: str
    toc: list["SectionPlan"]
    current_section_idx: int
    sections: list["SectionDraft"]
    final_document: str
    error: Optional[str]
    status: str
    events: list[str]


class GenerationState(dict):
    """
    TypedDict-compatible state for LangGraph.
    Using a plain dict subclass for maximum LangGraph compatibility.

    Keys:
        artifact_type       : "BRD" | "FSD" | "TSD"
        reference_summary   : Short summary of uploaded docs
        toc                 : List[SectionPlan] — from planning node
        current_section_idx : int — pointer into toc
        sections            : List[SectionDraft] — accumulates across loop
        final_document      : str — assembled markdown output
        error               : Optional[str]
        status              : "planning" | "generating" | "compiling" | "done" | "error"
        events              : List[str] — SSE event log for frontend streaming
    """

    @classmethod
    def initial(cls, artifact_type: str) -> "GenerationState":
        state = cls()
        state["artifact_type"] = artifact_type
        state["reference_summary"] = ""
        state["toc"] = []
        state["current_section_idx"] = 0
        state["sections"] = []
        state["final_document"] = ""
        state["error"] = None
        state["status"] = "planning"
        state["events"] = []
        return state

    def current_section_plan(self) -> Optional[SectionPlan]:
        toc = self["toc"]
        idx = self["current_section_idx"]
        if idx < len(toc):
            return toc[idx]
        return None

    def is_generation_complete(self) -> bool:
        return self["current_section_idx"] >= len(self["toc"])

    def current_draft(self) -> Optional[SectionDraft]:
        sections = self["sections"]
        idx = self["current_section_idx"]
        if idx < len(sections):
            return sections[idx]
        return None

    def emit(self, event: str) -> None:
        self["events"].append(event)
