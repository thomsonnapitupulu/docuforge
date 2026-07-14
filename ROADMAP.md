# DocuForge Roadmap

Phased plan reflecting the actual current state of the code (not aspirational). Update this
file as items complete — check items off in the same commit that finishes the work.

## Phase 0 — Foundations (mostly done)

Ingestion pipeline, chunking, embedding, the LangGraph generation loop, FastAPI routes, and
basic React pages all exist and appear functionally complete for a single-user local MVP.

- [x] Document parsing (PDF/DOCX/MD/TXT) — `backend/ingestion/parser.py`
- [x] Hierarchical parent/child chunking — `backend/ingestion/chunker.py`
- [x] Chroma embedding + stats — `backend/ingestion/embedder.py`
- [x] LangGraph generation loop (plan → retrieve → draft → critique → retry → compile) —
      `backend/graph/`
- [x] FastAPI routes for ingest/generate/status/stream/export — `backend/api/main.py`
- [x] React pages for upload/generate/preview — `frontend/src/pages/`
- [x] Reconcile `README.md`'s documented file tree with reality (`backend/utils/logger.py`
      now exists — built in Phase 1, see below)
- [x] Commit the currently-pending `backend/requirements.txt` change
- [x] Confirm `.gitignore` excludes `chroma_db/`, `node_modules/`, `.env` (done this session)

## Phase 1 — Hardening the core loop

- [x] Implement `backend/utils/logger.py` (structured logging setup) and wire it into
      `api/main.py`, `graph/nodes.py`, and `ingestion/*.py` instead of ad-hoc
      `structlog.get_logger()` calls — verified live via a real `/ingest` request
- [x] Add backend tests: `ingestion/parser.py`, `ingestion/chunker.py`, and the conditional
      routing logic (`route_after_evaluation`, `route_after_advance`, `advance_section`) —
      `backend/tests/`, run with `pytest` from `backend/` (venv active). 20 tests passing.
- [x] Add basic error surfacing in the frontend — `GeneratePage.jsx` now uses `api.streamJob()`
      (was hardcoding `localhost:8000`, bypassing `VITE_API_URL`), surfaces the backend's
      `{"error": ...}` SSE payload (previously silently ignored), and has a "Try again" action
      instead of requiring a page reload
- [x] Manually verify the `/jobs/{id}/stream` SSE flow end-to-end against a live backend —
      done via Playwright driving the real UI through upload → generate; also caught a real
      backend failure live (see new item below), confirming the error path works against a
      genuine failure, not just a simulated one
- [ ] **Newly discovered**: `graph/builder.py` has no conditional routing after `plan_document`
      to handle TOC-parsing failures — when the LLM's TOC JSON is truncated or malformed
      (observed live: `max_tokens=2000` was too low for a full section list, producing
      "Unterminated string" `json.JSONDecodeError`), the graph unconditionally proceeds to
      `retrieve_context` against an empty/error `toc`, crashing instead of ending in a clean
      `"status": "error"` state. Fix: either raise `plan_document`'s `max_tokens`, or add a
      conditional edge from `plan_document` straight to `END`/`compile_document` when
      `state["error"]` is set.

## Phase 2 — Persistence & reliability

- [ ] Replace the in-memory `_jobs` dict in `api/main.py` with durable storage (SQLite is
      the simplest fit for a single-instance deployment; Redis if concurrent workers are needed)
- [ ] Add retry/backoff around Anthropic API calls in `graph/nodes.py` (`_llm` helper)
- [ ] Add job cancellation (currently no way to stop an in-flight `/generate` job)

## Phase 3 — Frontend completeness

- [ ] Verify the full Upload → Generate → Preview flow against a running backend in a browser
- [ ] Add loading/error states across all three pages
- [ ] Polish export UX (`/jobs/{id}/export?format=docx|md`) — confirm download behavior and
      filename handling in `PreviewPage.jsx`

## Phase 4 — Productionization

- [ ] Auth (only if/when multi-user access is needed — not required for single-user local use)
- [ ] Rate limiting on `/ingest` and `/generate`
- [ ] Deployment config (Dockerfile / docker-compose for backend + Chroma persistence volume)
- [ ] CI (lint + backend test suite from Phase 1)
- [ ] Secrets management guidance beyond local `.env` (e.g. for a hosted deployment)
