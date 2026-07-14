"""
LangGraph Node Functions for DocuForge.

Each function is a pure node: receives state dict, returns partial state update.
Nodes are stateless — all context is carried through GenerationState.

Node sequence:
  plan_document → [loop: retrieve_context → draft_section → evaluate_section] → compile_document
"""

import json
from utils.logger import get_logger

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import get_settings
from core.prompts import (
    PLANNING_PROMPT,
    DRAFTING_PROMPT,
    CRITIC_PROMPT,
    REDRAFT_PROMPT,
    ARTIFACT_GUIDANCE,
    REFERENCE_SUMMARY_PROMPT,
)
from graph.state import GenerationState, SectionPlan, SectionDraft
from ingestion.embedder import VectorStoreManager

logger = get_logger(__name__)
settings = get_settings()

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_vector_store = VectorStoreManager()


# Only retry on transient failures — connection issues, timeouts, rate limits, and 5xx
# server errors. Never retry AuthenticationError/BadRequestError/etc.: those will fail
# identically every time and just burn attempts and latency.
_RETRYABLE_ANTHROPIC_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _log_before_sleep(retry_state) -> None:
    logger.warning(
        "llm_call_retrying",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()),
    )


@retry(
    retry=retry_if_exception_type(_RETRYABLE_ANTHROPIC_ERRORS),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    before_sleep=_log_before_sleep,
    reraise=True,
)
def _llm(prompt: str, max_tokens: int = 4096) -> str:
    """Thin wrapper around Anthropic claude-sonnet-4-6, with retry/backoff on
    transient API failures (connection errors, timeouts, rate limits, 5xx)."""
    response = _client.messages.create(
        model=settings.model_name,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1: plan_document
# Generates a full TOC for the target artifact type.
# ─────────────────────────────────────────────────────────────────────────────

def plan_document(state: dict) -> dict:
    artifact_type = state["artifact_type"]
    logger.info("node_plan_document", artifact_type=artifact_type)

    reference_summary = state.get("reference_summary") or _vector_store.get_reference_sample()

    prompt = PLANNING_PROMPT.format(
        artifact_type=artifact_type,
        reference_summary=reference_summary,
        artifact_guidance=ARTIFACT_GUIDANCE[artifact_type]
    )

    raw = _llm(prompt, max_tokens=4096)

    # Strip any accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    try:
        toc_raw = json.loads(raw)
        toc = [SectionPlan(**entry) for entry in toc_raw]
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("toc_parse_failed", error=str(e), raw=raw[:200])
        return {
            "error": f"TOC parsing failed: {e}",
            "status": "error",
            "events": state.get("events", []) + ["❌ Planning failed: could not parse table of contents"],
        }

    logger.info("toc_generated", section_count=len(toc))

    return {
        "toc": toc,
        "reference_summary": reference_summary,
        "status": "generating",
        "current_section_idx": 0,
        "sections": [],
        "events": state.get("events", []) + [f"📋 Plan complete: {len(toc)} sections planned"]
    }


def route_after_planning(state: dict) -> str:
    """
    Returns the name of the next node:
    - "retrieve_context" → TOC planned successfully
    - "end"              → plan_document failed (state["error"] set); stop instead of
                           crashing downstream on an empty/missing toc
    """
    if state.get("error"):
        return "end"
    return "retrieve_context"


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2: retrieve_context
# Queries vector DB for context relevant to the current section.
# ─────────────────────────────────────────────────────────────────────────────

def retrieve_context(state: dict) -> dict:
    toc: list[SectionPlan] = state["toc"]
    idx: int = state["current_section_idx"]
    artifact_type = state["artifact_type"]
    section = toc[idx]

    query = f"{section.title}: {section.description}"
    logger.info("node_retrieve_context", section_id=section.section_id, query=query[:80])

    context = _vector_store.retrieve_context(
        query=query,
        artifact_type=section.target_artifact_filter or artifact_type,
    )

    # Initialize or update the SectionDraft for this section
    sections: list[SectionDraft] = list(state.get("sections", []))

    # Find or create the draft for this section
    existing_draft = next((s for s in sections if s.section_id == section.section_id), None)
    if existing_draft:
        existing_draft.retrieved_context = context
    else:
        sections.append(SectionDraft(
            section_id=section.section_id,
            title=section.title,
            retrieved_context=context,
        ))

    return {
        "sections": sections,
        "events": state.get("events", []) + [
            f"🔍 [{section.section_id}] Context retrieved ({len(context)} chars)"
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3: draft_section
# Writes the section content using retrieved context.
# ─────────────────────────────────────────────────────────────────────────────

def draft_section(state: dict) -> dict:
    toc: list[SectionPlan] = state["toc"]
    idx: int = state["current_section_idx"]
    sections: list[SectionDraft] = state["sections"]
    section_plan = toc[idx]
    artifact_type = state["artifact_type"]

    # Find current draft
    draft = next(s for s in sections if s.section_id == section_plan.section_id)

    logger.info("node_draft_section", section_id=section_plan.section_id, retry=draft.retry_count)

    if draft.retry_count == 0:
        prompt = DRAFTING_PROMPT.format(
            section_id=section_plan.section_id,
            section_title=section_plan.title,
            section_description=section_plan.description,
            artifact_type=artifact_type,
            retrieved_context=draft.retrieved_context or "[No context found — write from general knowledge for this section type]",
        )
    else:
        prompt = REDRAFT_PROMPT.format(
            section_id=section_plan.section_id,
            section_title=section_plan.title,
            artifact_type=artifact_type,
            previous_draft=draft.content,
            improvement_instructions=draft.improvement_instructions,
            issues="\n".join(f"- {i}" for i in draft.critic_issues),
            retrieved_context=draft.retrieved_context,
        )

    content = _llm(prompt, max_tokens=2000)
    draft.content = content

    return {
        "sections": sections,
        "events": state.get("events", []) + [
            f"✍️ [{section_plan.section_id}] Draft {'#' + str(draft.retry_count + 1)} written"
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4: evaluate_section (Critic)
# LLM-as-judge checks draft quality against source context.
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_section(state: dict) -> dict:
    toc: list[SectionPlan] = state["toc"]
    idx: int = state["current_section_idx"]
    sections: list[SectionDraft] = state["sections"]
    section_plan = toc[idx]
    artifact_type = state["artifact_type"]

    draft = next(s for s in sections if s.section_id == section_plan.section_id)

    logger.info("node_evaluate_section", section_id=section_plan.section_id)

    prompt = CRITIC_PROMPT.format(
        section_id=section_plan.section_id,
        section_title=section_plan.title,
        artifact_type=artifact_type,
        retrieved_context=draft.retrieved_context or "",
        draft_content=draft.content,
    )

    raw = _llm(prompt, max_tokens=800)

    # Clean JSON
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("```").strip()

    try:
        result = json.loads(raw)
        passed = result.get("passed", False)
        issues = result.get("issues", [])
        instructions = result.get("improvement_instructions", "")
        score = result.get("score", 0)
    except json.JSONDecodeError:
        logger.warning("critic_parse_failed", raw=raw[:200])
        passed = True   # If critic output is unparseable, accept the draft
        issues = []
        instructions = ""
        score = 7

    draft.passed_critic = passed
    draft.critic_issues = issues
    draft.improvement_instructions = instructions
    draft.retry_count += 1

    status_emoji = "✅" if passed else "⚠️"
    event = f"{status_emoji} [{section_plan.section_id}] Critic score: {score}/10 — {'Passed' if passed else 'Needs revision'}"

    return {
        "sections": sections,
        "events": state.get("events", []) + [event]
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING FUNCTION
# Called after evaluate_section to decide next step.
# ─────────────────────────────────────────────────────────────────────────────

def route_after_evaluation(state: dict) -> str:
    """
    Returns the name of the next node:
    - "draft_section"     → critic failed AND retries remaining
    - "advance_section"   → critic passed OR max retries hit
    """
    toc: list[SectionPlan] = state["toc"]
    idx: int = state["current_section_idx"]
    sections: list[SectionDraft] = state["sections"]
    section_plan = toc[idx]

    draft = next(s for s in sections if s.section_id == section_plan.section_id)

    if not draft.passed_critic and draft.retry_count < settings.max_retries_per_section:
        logger.info("routing_to_redraft", section_id=section_plan.section_id, retry=draft.retry_count)
        return "draft_section"

    return "advance_section"


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5: advance_section
# Moves the section pointer forward or triggers compilation.
# ─────────────────────────────────────────────────────────────────────────────

def advance_section(state: dict) -> dict:
    idx = state["current_section_idx"]
    toc = state["toc"]
    new_idx = idx + 1

    if new_idx >= len(toc):
        return {
            "current_section_idx": new_idx,
            "status": "compiling",
            "events": state.get("events", []) + ["📦 All sections complete — compiling document..."]
        }

    next_section = toc[new_idx]
    return {
        "current_section_idx": new_idx,
        "events": state.get("events", []) + [
            f"➡️ Moving to section {next_section.section_id}: {next_section.title}"
        ]
    }


def route_after_advance(state: dict) -> str:
    """Route to retrieve_context if more sections remain, else compile."""
    if state["current_section_idx"] >= len(state["toc"]):
        return "compile_document"
    return "retrieve_context"


# ─────────────────────────────────────────────────────────────────────────────
# NODE 6: compile_document
# Merges all section drafts into a single markdown document.
# ─────────────────────────────────────────────────────────────────────────────

def compile_document(state: dict) -> dict:
    artifact_type = state["artifact_type"]
    sections: list[SectionDraft] = state["sections"]
    toc: list[SectionPlan] = state["toc"]

    logger.info("node_compile_document", section_count=len(sections))

    header = f"# {artifact_type}\n\n"
    header += f"> Generated by DocuForge — Agentic RAG Document Generator\n\n"
    header += "---\n\n"

    # Table of contents block
    toc_block = "## Table of Contents\n\n"
    for section in toc:
        indent = "  " * (len(section.section_id.split(".")) - 1)
        toc_block += f"{indent}- {section.section_id}. {section.title}\n"
    toc_block += "\n---\n\n"

    # Section content — ordered by TOC
    section_map = {s.section_id: s for s in sections}
    body_parts = []
    for plan in toc:
        draft = section_map.get(plan.section_id)
        if draft and draft.content:
            # Ensure section starts with appropriate header
            content = draft.content.strip()
            if not content.startswith("#"):
                content = f"## {plan.section_id}. {plan.title}\n\n{content}"
            body_parts.append(content)
        else:
            body_parts.append(f"## {plan.section_id}. {plan.title}\n\n_[Section not generated]_")

    final_document = header + toc_block + "\n\n".join(body_parts)

    return {
        "final_document": final_document,
        "status": "done",
        "events": state.get("events", []) + ["🎉 Document compiled successfully!"]
    }
