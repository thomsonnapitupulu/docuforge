"""
DocuForge FastAPI Application.

Routes:
  POST /ingest              — Upload and index reference documents
  POST /generate            — Kick off document generation job
  GET  /jobs/{job_id}       — Poll job status
  GET  /jobs/{job_id}/stream — SSE stream of generation events
  GET  /jobs/{job_id}/export — Download compiled document (md or docx)
  GET  /stats               — Vector store statistics
  DELETE /clear             — Wipe vector store
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

from api.job_store import JobStore
from api.rate_limit import RateLimiter, client_key
from api.schemas import (
    GenerateRequest, GenerateResponse,
    JobStatusResponse, IngestionResponse, StatsResponse
)
from core.config import get_settings
from ingestion.parser import DocumentParser
from ingestion.chunker import HierarchicalChunker
from ingestion.embedder import VectorStoreManager
from graph.builder import generation_graph
from graph.state import GenerationState
from utils.exporter import markdown_to_docx
from utils.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="DocuForge",
    description="Agentic RAG pipeline for BRD/FSD/TSD generation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────────────────
parser   = DocumentParser()
chunker  = HierarchicalChunker(
    child_chunk_tokens=settings.child_chunk_size,
    parent_chunk_tokens=settings.parent_chunk_size,
)
vector_store = VectorStoreManager()
job_store = JobStore(settings.job_db_path)
ingest_limiter = RateLimiter(settings.ingest_rate_limit_per_minute)
generate_limiter = RateLimiter(settings.generate_rate_limit_per_minute)


# ─────────────────────────────────────────────────────────────────────────────
# INGESTION
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestionResponse)
async def ingest_document(http_request: Request, file: UploadFile = File(...)):
    """Parse, chunk, and embed an uploaded reference document."""
    ingest_limiter.check(client_key(http_request))

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    file_bytes = await file.read()
    logger.info("ingest_request", filename=file.filename, size=len(file_bytes))

    try:
        raw_doc = parser.parse(file.filename, file_bytes)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e))

    chunks = chunker.chunk(raw_doc.filename, raw_doc.content)
    if not chunks:
        raise HTTPException(422, "Document produced no chunks — is it empty?")

    vector_store.upsert_chunks(chunks)

    parent_count = sum(1 for c in chunks if c.metadata["chunk_type"] == "parent")
    child_count  = sum(1 for c in chunks if c.metadata["chunk_type"] == "child")
    inferred     = chunks[0].metadata.get("target_artifact", "ALL") if chunks else "ALL"

    return IngestionResponse(
        filename=file.filename,
        chunks_created=len(chunks),
        parent_chunks=parent_count,
        child_chunks=child_count,
        inferred_target=inferred,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GENERATION
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse)
async def generate_document(body: GenerateRequest, http_request: Request, background_tasks: BackgroundTasks):
    """Kick off a document generation job in the background."""
    generate_limiter.check(client_key(http_request))

    stats = vector_store.collection_stats()
    if stats["child_chunks"] == 0:
        raise HTTPException(400, "No documents indexed. Please ingest reference documents first.")

    job_id = body.job_id or str(uuid.uuid4())

    job_store.create(job_id, body.artifact_type.value)

    background_tasks.add_task(_run_generation, job_id, body.artifact_type.value)

    return GenerateResponse(
        job_id=job_id,
        status="queued",
        message=f"{body.artifact_type.value} generation started. Poll /jobs/{job_id} for status."
    )


# LangGraph's default recursion_limit (25 super-steps) counts every node
# execution, not just sections — each section can take up to
# retrieve_context + (draft + evaluate) per attempt (1 initial + N retries) +
# advance_section. With PLANNING_PROMPT capped at 15 TOC entries (see
# core/prompts.py), the worst case is well above the default limit, so a
# real multi-section run reliably hit "Recursion limit ... reached" before
# this was added. Size the limit generously off the same constants instead
# of guessing a bigger fixed number.
_MAX_TOC_SECTIONS = 15  # keep in sync with PLANNING_PROMPT's size limit
_STEPS_PER_SECTION = 2 * (settings.max_retries_per_section + 1) + 2
GENERATION_RECURSION_LIMIT = _MAX_TOC_SECTIONS * _STEPS_PER_SECTION + 10  # + plan/compile buffer


def _run_graph_with_cancellation(job_id: str, initial_state: dict) -> dict:
    """
    Runs the graph step-by-step (instead of a single blocking .invoke()) so we
    can cooperatively check for a cancellation request between node executions.
    A synchronous LangGraph invoke() can't be interrupted mid-flight without
    killing the thread, so cancellation takes effect at the next node boundary,
    not instantly.
    """
    final_state = initial_state
    stream = generation_graph.stream(
        initial_state,
        stream_mode="values",
        config={"recursion_limit": GENERATION_RECURSION_LIMIT},
    )
    for state in stream:
        final_state = state
        current_job = job_store.get(job_id)
        if current_job and current_job["status"] == "cancelling":
            return {**final_state, "status": "cancelled", "error": "Cancelled by user"}
    return final_state


async def _run_generation(job_id: str, artifact_type: str):
    """Background task: runs the LangGraph pipeline and updates job store."""
    try:
        initial_state = GenerationState.initial(artifact_type)

        # Run the graph — this is synchronous LangGraph; wrap in executor
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(
            None,
            lambda: _run_graph_with_cancellation(job_id, initial_state)
        )

        toc = final_state.get("toc", [])
        sections = final_state.get("sections", [])
        status = final_state.get("status", "done")

        job_store.update(
            job_id,
            status=status,
            total_sections=len(toc),
            sections_complete=len([s for s in sections if s.passed_critic or s.retry_count >= settings.max_retries_per_section]),
            events=final_state.get("events", []),
            final_document=final_state.get("final_document", ""),
            error=final_state.get("error"),
        )

        logger.info("generation_complete", job_id=job_id, status=status)

    except Exception as e:
        logger.error("generation_error", job_id=job_id, error=str(e))
        job_store.update(job_id, status="error", error=str(e))


@app.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(job_id: str):
    """Request cancellation of an in-flight generation job. Takes effect at
    the next node boundary in the graph, not instantly."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job["status"] != "running":
        raise HTTPException(400, f"Job is not running (status: {job['status']}) — nothing to cancel")

    job_store.update(job_id, status="cancelling")
    logger.info("job_cancel_requested", job_id=job_id)
    return JobStatusResponse(**job_store.get(job_id))


# ─────────────────────────────────────────────────────────────────────────────
# JOB STATUS & STREAMING
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Poll for job status and progress."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return JobStatusResponse(**job)


@app.get("/jobs/{job_id}/stream")
async def stream_job_events(job_id: str):
    """
    Server-Sent Events stream for live progress updates.
    Clients can connect and receive events as each section completes.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        sent_count = 0
        while True:
            job = job_store.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            events = job.get("events", [])
            # Send any new events since last poll
            for event in events[sent_count:]:
                yield f"data: {json.dumps({'event': event})}\n\n"
            sent_count = len(events)

            # Send progress
            yield f"data: {json.dumps({'status': job['status'], 'sections_complete': job['sections_complete'], 'total_sections': job['total_sections']})}\n\n"

            if job["status"] in ("done", "error", "cancelled"):
                yield f"data: {json.dumps({'done': True, 'status': job['status']})}\n\n"
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/jobs/{job_id}/export")
async def export_document(job_id: str, format: str = "md"):
    """Download the completed document as Markdown or DOCX."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job is not complete yet (status: {job['status']})")

    doc_content = job["final_document"] or ""
    artifact_type = job["artifact_type"]
    filename_base = f"{artifact_type}_{job_id[:8]}"

    if format == "docx":
        docx_bytes = markdown_to_docx(doc_content, title=artifact_type)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.docx"'}
        )

    # Default: markdown
    return Response(
        content=doc_content.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.md"'}
    )


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Return vector store document counts."""
    return StatsResponse(**vector_store.collection_stats())


@app.delete("/clear")
async def clear_vector_store():
    """Wipe all indexed chunks. Use with caution."""
    vector_store.clear_all()
    return {"message": "Vector store cleared"}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
