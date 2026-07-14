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
    └── exporter.py       Markdown -> DOCX conversion

frontend/src/
├── pages/UploadPage.jsx, GeneratePage.jsx, PreviewPage.jsx
├── lib/api.js            Backend API client
└── App.jsx, main.jsx
```

Note: the original README's tree mentions `backend/utils/logger.py` — this file does not
currently exist (only `exporter.py` is under `utils/`). Structured logging today is done
inline via `structlog` in `api/main.py` and `graph/nodes.py`. Don't assume `logger.py` exists;
check before importing from it.

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

## Known constraints / conventions

- **Job store is in-memory** (`_jobs` dict in `api/main.py`) — restarting the backend loses
  all job state. Don't treat job history as durable until this is replaced (tracked in
  `ROADMAP.md` Phase 2).
- **No test suite yet** for backend or frontend. Be extra careful with changes to
  `graph/nodes.py` and `graph/builder.py` routing logic since there's no automated safety net.
- **`backend/chroma_db/`** is local vector store data, not source — it's gitignored, never
  hand-edit or commit it.
- **`.env`** holds `ANTHROPIC_API_KEY` and other secrets — never read its contents into a
  commit, log message, or chat output.
- Model in use: `claude-sonnet-4-6` (via `anthropic` SDK), configured in `backend/core/config.py`.
