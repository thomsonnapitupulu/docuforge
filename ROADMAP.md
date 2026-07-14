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
- [x] Bounded the oversized TOC — `PLANNING_PROMPT` (`core/prompts.py`) had produced 30-40
      sections for a single small BRD test doc (seen twice), each costing 1-3 LLM round trips.
      Added an explicit size limit (≤15 entries total, ≤2 subsections per top-level section,
      only split when the material justifies it). Verified live with real LLM calls: 12-13
      sections now, run twice and across all three artifact types (BRD/FSD/TSD), down from
      30-40.
- [x] Fixed `.gitignore`'s bare `lib/` rule (meant for Python's root-level `lib/`/`lib64/`
      packaging dirs) which, with no leading slash, matched `lib/` at ANY depth — silently
      excluding `frontend/src/lib/api.js` from git entirely since the very first commit. Fixed
      by anchoring to `/lib/`, `/lib64/` and adding the directory to version control. Audited
      the rest of `.gitignore` via `git status --ignored` — no other project source files are
      unexpectedly excluded (only `.claude/`, which is intentional).
- [x] **Newly discovered (while verifying Phase 3)**: LangGraph's default `recursion_limit`
      (25 super-steps) was far too low for even the now-bounded 12-15 section TOC — each
      section can take ~10 steps in the worst case (retrieve + draft/evaluate per retry +
      advance), so a real 12-section run crashed with "Recursion limit of 25 reached." Added
      `GENERATION_RECURSION_LIMIT` in `api/main.py`, computed from the same constants
      `PLANNING_PROMPT` enforces. Regression tests in `test_recursion_limit.py` prove the bug
      at small scale (3 sections forced through max retries) and that the fix resolves it.
      Verified live: a real 12-section generation completed end-to-end for the first time all
      session — see Phase 3 below.

## Phase 3 — Frontend completeness

- [x] Verify the full Upload → Generate → Preview flow against a running backend in a browser
      — done via Playwright driving the real UI through a complete real generation (12
      sections, ~8 min, real Anthropic API calls) all the way to a rendered 47k-character BRD
      on the Preview page. This surfaced and led to fixing the recursion-limit bug above.
- [x] Add loading/error states across all three pages — `UploadPage.jsx`'s `api.getStats()`
      call was unguarded; if it threw, `setUploading(false)` never ran, leaving the UI stuck on
      "Indexing…" forever even after ingestion itself had already succeeded/failed. Wrapped in
      try/finally. `PreviewPage.jsx` had no error handling at all for clipboard or download
      failures — added both (see item below).
- [x] Polish export UX (`/jobs/{id}/export?format=docx|md`) — `PreviewPage.jsx` used
      `window.open()` directly, so a failed export (backend down, job not done) silently opened
      a blank tab with no feedback. Switched to fetch+blob downloads with proper error
      surfacing, per-button loading state, and filenames read from the real
      `Content-Disposition` header. Verified live: real Copy Markdown / .md / .docx downloads
      all worked with correct filenames, and a deliberately-aborted export request correctly
      showed an in-app "Failed to fetch" banner instead of a silent broken tab.

## Phase 4 — Productionization

- [ ] Auth (only if/when multi-user access is needed — not required for single-user local use)
- [ ] Rate limiting on `/ingest` and `/generate`
- [ ] Deployment config (Dockerfile / docker-compose for backend + Chroma persistence volume)
- [ ] CI (lint + backend test suite from Phase 1)
- [ ] Secrets management guidance beyond local `.env` (e.g. for a hosted deployment)
