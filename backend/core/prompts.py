"""
All prompt templates for DocuForge's generation pipeline.
Separated from logic for easy tuning without touching orchestration code.
"""

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: DOCUMENT PLANNING
# Generates a structured Table of Contents for the chosen artifact type.
# ─────────────────────────────────────────────────────────────────────────────

PLANNING_PROMPT = """You are a senior technical writer generating a {artifact_type} document.

Below is a summary of the available reference documents:
<reference_summary>
{reference_summary}
</reference_summary>

Your task: Generate a right-sized, structured Table of Contents (TOC) for a {artifact_type}.

Rules:
- Output ONLY a valid JSON array. No prose, no markdown fences.
- Each entry must have: "section_id" (e.g. "3.2"), "title", "description" (one sentence), "target_artifact_filter" (for vector DB metadata filtering)
- Depth: top-level sections (1, 2, 3...) and subsections (1.1, 1.2...) only. No deeper nesting.
- Size limit: the TOC must have AT MOST 15 entries total (top-level sections + subsections
  combined), and never more than 2 subsections under any single top-level section. Each
  section is drafted with its own LLM call, so an oversized TOC wastes time and cost without
  adding value — stay as close to the required section list below as the material allows.
- Only add a subsection when the reference material actually contains enough distinct content
  to justify splitting a topic. Otherwise keep it as a single top-level section.
- Tailor the sections precisely for {artifact_type}:

{artifact_guidance}

Output format:
[
  {{
    "section_id": "1",
    "title": "Executive Summary",
    "description": "High-level overview of the project scope and business objectives.",
    "target_artifact_filter": "BRD"
  }},
  ...
]"""

ARTIFACT_GUIDANCE = {
    "BRD": """
BRD must include:
- Executive Summary
- Business Objectives & Success Metrics
- Stakeholder Analysis & User Personas
- Current State / Problem Statement
- Proposed Solution Scope
- Business Constraints & Assumptions
- Regulatory & Compliance Requirements
- High-Level Timeline & Milestones
- Risk Register
- Sign-off & Approval Matrix""",

    "FSD": """
FSD must include:
- Document Purpose & Scope
- System Overview & Context Diagram
- User Roles & Permissions Matrix
- Functional Requirements (grouped by feature module)
- User Interface Specifications
- Business Rules & Validation Logic
- Integration Points & External Dependencies
- Error Handling & Edge Case Catalogue
- Non-Functional Requirements
- Acceptance Criteria""",

    "TSD": """
TSD must include:
- Architecture Overview & Design Decisions
- Technology Stack & Justification
- Data Models & Entity Relationships
- API Contracts (endpoints, request/response schemas)
- Authentication & Authorization Flows
- Infrastructure & Deployment Topology
- Performance & Scalability Design
- Security Controls & Threat Model
- Observability (Logging, Metrics, Alerts)
- Migration & Rollback Strategy"""
}


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: SECTION DRAFTING
# Writes one section at a time using retrieved context.
# ─────────────────────────────────────────────────────────────────────────────

DRAFTING_PROMPT = """You are writing section {section_id}: "{section_title}" for a {artifact_type} document.

Retrieved context from reference documents:
<context>
{retrieved_context}
</context>

Section description: {section_description}

Instructions:
- Write comprehensive, precise content for this section only.
- Use formal technical writing style appropriate for {artifact_type}.
- Reference specific details from the provided context. Do NOT hallucinate data.
- Use markdown formatting: headers (##, ###), tables, bullet lists, code blocks where appropriate.
- If the context does not contain enough information for a part of this section, explicitly note: "[INFORMATION REQUIRED: <what is missing>]"
- Length: 300–800 words depending on section complexity.

Begin writing section {section_id} now:"""


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: CRITIC EVALUATION
# LLM-as-a-judge. Evaluates draft against source material.
# ─────────────────────────────────────────────────────────────────────────────

CRITIC_PROMPT = """You are a strict technical document reviewer evaluating a draft section.

Original reference context used:
<context>
{retrieved_context}
</context>

Draft section to evaluate:
<draft>
{draft_content}
</draft>

Section being evaluated: {section_id} - "{section_title}" for a {artifact_type}

Evaluate against these criteria:
1. ACCURACY: All factual claims are grounded in the reference context. No hallucinations.
2. COMPLETENESS: All key points from the context relevant to this section are covered.
3. SPECIFICITY: Uses concrete details, numbers, names from source — not vague generalities.
4. FORMAT: Appropriate markdown structure, tables/lists where needed.
5. NO_GAPS: No critical edge cases or constraints from the source are omitted.

Respond ONLY with valid JSON:
{{
  "passed": true | false,
  "score": 1-10,
  "issues": ["issue 1", "issue 2"],
  "improvement_instructions": "Specific, actionable rewrite instructions if failed. Empty string if passed."
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: RE-DRAFT (with critic feedback)
# ─────────────────────────────────────────────────────────────────────────────

REDRAFT_PROMPT = """You are rewriting section {section_id}: "{section_title}" for a {artifact_type}.

Previous draft that FAILED review:
<previous_draft>
{previous_draft}
</previous_draft>

Critic feedback:
<feedback>
{improvement_instructions}
</feedback>

Issues identified:
{issues}

Reference context:
<context>
{retrieved_context}
</context>

Rewrite the section addressing ALL critic feedback. Be precise and grounded in the context:"""


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE SUMMARY GENERATION
# Produces a short summary of uploaded docs for the planning phase.
# ─────────────────────────────────────────────────────────────────────────────

REFERENCE_SUMMARY_PROMPT = """Summarize the following technical reference documents in 200–300 words.
Focus on: the system being described, key technical components, business domain, and any explicit constraints.
This summary will be used to plan a formal document TOC.

Documents:
{documents_text}

Summary:"""
