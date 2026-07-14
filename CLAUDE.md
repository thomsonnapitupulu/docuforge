# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

DocuForge is an agentic RAG pipeline that generates enterprise documents (BRD, FSD, TSD)
from uploaded reference material (PDF/DOCX/MD/TXT). Docs are parsed, hierarchically chunked,
embedded into ChromaDB, then a LangGraph state machine plans a table of contents, retrieves
context per section, drafts, self-critiques, retries on failure, and compiles the final
document for export as Markdown or DOCX.

For the commit/workflow policy (when to stage and commit, and that pushing is off-limits
for agents), see `AGENTS.md`. For what's built vs. what's still planned, see `ROADMAP.md`.

## Architecture principle

Favor cost-optimized, simple architecture with the fewest possible dependent services/tools.
Prefer proven, widely-adopted tech over niche or trendy alternatives. When choosing between
options (e.g. job persistence, deployment infra), default to the one with the fewest moving
parts and broadest market adoption — justify any added service/dependency against this bar
before introducing it. Chroma (embedded, no separate server) and SQLite (over Redis/Postgres)
are examples of the right call under this constraint; see `ROADMAP.md` Phase 2/4.

## Architecture

```
backend/
├── api/
│   ├── main.py          FastAPI app: /ingest, /generate, /jobs/{id}, /jobs/{id}/stream (SSE),
│   │                    /jobs/{id}/export, /stats, /clear, /health
│   ├── job_store.py     SQLite-backed job store (JobStore) — survives backend restarts
│   ├── rate_limit.py    In-memory sliding-window rate limiter (per client IP)
│   └── schemas.py       Pydantic request/response models
├── core/
│   ├── config.py        Settings via pydantic-settings, reads backend/.env
│   └── prompts.py        Planning / drafting / critic / redraft prompt templates
├── ingestion/
│   ├── parser.py         PDF/DOCX/MD/TXT -> raw text
│   ├── chunker.py        Hierarchical parent/child chunking
│   └── embedder.py       Chroma upsert + collection stats (VectorStoreManager)
├── graph/
│   ├── state.py          GenerationState dict + SectionPlan/SectionDraft dataclasses
│   ├── nodes.py          plan_document -> retrieve_context -> draft_section ->
│   │                     evaluate_section -> advance_section -> compile_document
│   └── builder.py         Assembles the LangGraph StateGraph with retry/advance routing
└── utils/
    ├── exporter.py       Markdown -> DOCX conversion
    └── logger.py         Shared structlog config (configure_logging/get_logger)

frontend/src/
├── pages/UploadPage.jsx, GeneratePage.jsx, PreviewPage.jsx
├── lib/api.js            Backend API client
└── App.jsx, main.jsx
```

## Running locally

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set ANTHROPIC_API_KEY
uvicorn api.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Both dev servers are commonly left running across sessions on ports 8000 and 5173 — check
for existing listeners (`lsof -nP -iTCP -sTCP:LISTEN`) before starting new ones, and kill
stale ones rather than stacking duplicates.

Via Docker (backend only):
```bash
docker compose up -d --build
```
Single container — no Redis/Postgres/separate services. `CHROMA_PERSIST_DIR` and
`JOB_DB_PATH` are both pointed at one named volume (`docuforge_data`) by
`docker-compose.yml`, so vector data and job state both survive container restarts.
`backend/Dockerfile` bakes Chroma's embedding model into the image at build time (see
below) — a container built this way has zero cold-start latency.

Backend tests:
```bash
cd backend
source venv/bin/activate           # or .venv, whichever this checkout uses
pytest                             # runs backend/tests/, ~47 tests
ruff check .                       # lint — same check CI runs
```
`backend/tests/conftest.py` points Chroma at a throwaway tmp dir and sets a dummy
`ANTHROPIC_API_KEY` if one isn't already set, so running tests never touches
`backend/chroma_db/` or requires a real API key.

CI (`.github/workflows/ci.yml`) runs `ruff check` + `pytest` on every push/PR — no secrets
required. When writing a test that hits `/ingest` for real, stub out
`vector_store.upsert_chunks` unless you're specifically testing embedding — Chroma's default
embedding function downloads an ONNX model on first use, which is fast once cached locally but
took 60-90+ seconds on a clean CI container and made an unrelated rate-limit test flaky.

## Known constraints / conventions

- **Job store is SQLite** (`api/job_store.py`, path configurable via `JOB_DB_PATH`, default
  `./jobs.db`) — job state now survives backend restarts. It's gitignored like `chroma_db/`;
  never hand-edit or commit it. A running job can be stopped via
  `POST /jobs/{job_id}/cancel` — cancellation is cooperative and takes effect at the next
  LangGraph node boundary, not instantly (see `_run_graph_with_cancellation` in `api/main.py`).
- **LLM calls retry on transient failures**: `graph/nodes.py`'s `_llm()` wraps every Anthropic
  call with `tenacity`, retrying connection errors/timeouts/rate-limits/5xx with exponential
  backoff (up to 4 attempts). Non-transient errors (auth, bad request) are never retried.
- **`PLANNING_PROMPT`'s TOC size is capped at 15 entries** (≤2 subsections per top-level
  section) — without this, real runs produced 30-40 sections for a tiny test doc. If you
  change this cap, also update `GENERATION_RECURSION_LIMIT` in `api/main.py`, which is
  computed from it — LangGraph's default `recursion_limit` (25 super-steps) is far too low for
  a multi-section run with retries (each section can cost ~10 steps), and a real run hit that
  exact crash this session before the limit was raised.
- **`/ingest` and `/generate` are rate-limited** per client IP (`api/rate_limit.py`, in-memory,
  single-instance only — see its docstring). Configurable via `INGEST_RATE_LIMIT_PER_MINUTE`
  (default 20) and `GENERATE_RATE_LIMIT_PER_MINUTE` (default 5).
- **Chroma's embedding model is warmed up, not lazy-loaded on first request.**
  `VectorStoreManager.warm_up()` (`ingestion/embedder.py`) is called from a FastAPI lifespan
  handler in the background at startup, and — the real fix — `backend/Dockerfile` bakes the
  model into the image at build time. Don't remove either without understanding why: the model
  downloads to `~/.cache/chroma/onnx_models`, a *user-level* cache independent of
  `CHROMA_PERSIST_DIR`, so it's easy to not notice this matters in local dev (already cached)
  and only discover it in a fresh container/CI run, where it costs 60-90+ seconds.
- **Backend test coverage is partial**: `ingestion/parser.py`, `ingestion/chunker.py`, and
  the graph routing functions (`route_after_evaluation`, `route_after_advance`,
  `advance_section`, `route_after_planning`) are covered, plus a full mocked graph invocation
  in `test_graph_integration.py`. The LLM-calling node internals (prompt content/quality) and
  the frontend have no automated tests yet.
- **Always use `GenerationStateSchema` (a `TypedDict`, defined in `graph/state.py`) as the
  `StateGraph(...)` schema in `graph/builder.py` — never plain `dict`.** A plain, un-annotated
  `dict` schema makes LangGraph treat state as one opaque channel that gets wholesale-replaced
  by every node's return value, silently dropping any key a node didn't re-include. Since
  every node in `graph/nodes.py` returns only a partial update, this previously meant no
  generation could complete past the first node at all — see `test_graph_integration.py` for
  the regression test that guards against reintroducing this.
- **`backend/chroma_db/`** is local vector store data, not source — it's gitignored, never
  hand-edit or commit it.
- **`.env`** holds `ANTHROPIC_API_KEY` and other secrets — never read its contents into a
  commit, log message, or chat output.
- **This repo's `.gitignore` is large and templated** (covers many ecosystems this project
  doesn't use). It previously had a bare `lib/` rule that silently excluded
  `frontend/src/lib/api.js` from git entirely since the first commit — fixed by anchoring it
  to `/lib/` (repo root only). If a tracked-looking file mysteriously never shows up in
  `git status` after an edit, check `git check-ignore -v <path>` before assuming it's fine.
- Model in use: `claude-sonnet-4-6` (via `anthropic` SDK), configured in `backend/core/config.py`.
