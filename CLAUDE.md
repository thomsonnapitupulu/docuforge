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

Backend tests:
```bash
cd backend
source venv/bin/activate           # or .venv, whichever this checkout uses
pytest                             # runs backend/tests/, ~25 tests
```
`backend/tests/conftest.py` points Chroma at a throwaway tmp dir and sets a dummy
`ANTHROPIC_API_KEY` if one isn't already set, so running tests never touches
`backend/chroma_db/` or requires a real API key.

## Known constraints / conventions

- **Job store is in-memory** (`_jobs` dict in `api/main.py`) — restarting the backend loses
  all job state. Don't treat job history as durable until this is replaced (tracked in
  `ROADMAP.md` Phase 2).
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
- Model in use: `claude-sonnet-4-6` (via `anthropic` SDK), configured in `backend/core/config.py`.
