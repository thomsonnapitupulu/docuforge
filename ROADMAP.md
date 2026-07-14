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
- [ ] Reconcile `README.md`'s documented file tree with reality (it lists
      `backend/utils/logger.py`, which doesn't exist — either build it in Phase 1 or update
      the README to not reference it)
- [ ] Commit the currently-pending `backend/requirements.txt` change
- [x] Confirm `.gitignore` excludes `chroma_db/`, `node_modules/`, `.env` (done this session)

## Phase 1 — Hardening the core loop

- [ ] Implement `backend/utils/logger.py` (structured logging setup) and wire it into
      `api/main.py` / `graph/nodes.py` instead of ad-hoc `structlog.get_logger()` calls
- [ ] Add backend tests: `ingestion/parser.py`, `ingestion/chunker.py`, and the conditional
      routing logic in `graph/builder.py` (`route_after_evaluation`, `route_after_advance`)
- [ ] Add basic error surfacing in the frontend (currently unverified how `GeneratePage.jsx`
      handles a failed job or a dropped SSE stream)
- [ ] Manually verify the `/jobs/{id}/stream` SSE flow end-to-end against a live backend

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
