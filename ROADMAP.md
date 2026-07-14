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
- [x] Fixed `plan_document` TOC-parsing crash, and a much bigger root cause behind it:
      `graph/builder.py` compiled `StateGraph(dict)` — a plain, un-annotated dict schema —
      which LangGraph treats as a single opaque channel and **wholesale-replaces on every
      node call**, since every node only returns a partial update. This silently dropped
      `artifact_type`/`toc`/etc. after the very first node ran, meaning no generation could
      ever complete past `plan_document` at all (proven with a minimal repro in
      `backend/tests/test_graph_integration.py`). Fixed by introducing
      `GenerationStateSchema` (a proper `TypedDict`) in `graph/state.py` and using it as the
      graph schema instead of plain `dict`, so LangGraph merges per-key. Also added
      `route_after_planning()` so a malformed TOC ends cleanly in `"status": "error"` instead
      of crashing downstream, and raised planning's `max_tokens` 2000 → 4096. Verified live:
      reran the original crash scenario (now ends cleanly), ran a full mocked happy path to
      completion, and drove a real generation through the browser against the live Anthropic
      API — state now correctly survives 8+ real node transitions including retry/redraft
      cycles.

## Phase 2 — Persistence & reliability

- [x] Replace the in-memory `_jobs` dict in `api/main.py` with durable storage — added
      `backend/api/job_store.py` (stdlib `sqlite3`, no new dependency/service). Verified live:
      killed the backend mid-generation and restarted it; the job's status was still there
      instead of 404 Job not found. 6 new tests in `backend/tests/test_job_store.py`.
- [x] Add retry/backoff around Anthropic API calls — `graph/nodes.py`'s `_llm()` now wrapped
      with `tenacity` (already an unused dependency, no new package), retrying only transient
      errors (connection/timeout/rate-limit/5xx) with exponential backoff, up to 4 attempts.
      Verified live: injected transient failures into every LLM call in a full graph run — all
      transparently retried, pipeline still completed. 3 new tests in `test_llm_retry.py`.
- [x] Add job cancellation — `POST /jobs/{job_id}/cancel` + cooperative cancellation in
      `_run_generation` (switched `.invoke()` → `.stream(..., stream_mode="values")`, checking
      job status after each node). Frontend `GeneratePage.jsx` has a Cancel button while running.
      Verified live: cancelled a real 40-section run while `plan_document`'s LLM call was still
      in flight — stopped cleanly at `status=cancelled` right after that node, before any
      section drafting began. 5 new tests in `test_job_cancellation.py`.
- [ ] **Newly observed**: `PLANNING_PROMPT` (`core/prompts.py`) produced a 30-40 section TOC
      for a single small BRD test doc (seen twice now) — each section costs 1-3 LLM round trips
      (draft + critique + retries), so a real run can take 15-20+ minutes and a lot of API
      spend. Worth tuning the prompt to bound section count relative to reference doc size/
      complexity. (Job cancellation above makes this less costly to hit, but doesn't fix the
      root over-generation behavior.)
- [ ] **Newly discovered**: `.gitignore` had a bare `lib/` rule (meant for Python's root-level
      `lib/`/`lib64/` packaging dirs) that, with no leading slash, matched `lib/` at ANY depth —
      silently excluding `frontend/src/lib/api.js` from git entirely, since the very first
      commit. Fixed by anchoring to `/lib/`, `/lib64/` and adding the directory to version
      control. Worth double-checking no other files were silently excluded by an overly broad
      pattern in this `.gitignore` (it's a large, likely-templated file with rules for many
      ecosystems this project doesn't use).

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
