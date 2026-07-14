# DocuForge 🏗️

> Agentic RAG pipeline for generating enterprise-grade BRD, FSD, and TSD documents from raw technical references.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      DocuForge                          │
│                                                         │
│  ┌─────────┐    ┌──────────┐    ┌────────────────────┐ │
│  │ Ingest  │───▶│  Vector  │───▶│  LangGraph Engine  │ │
│  │Pipeline │    │   Store  │    │  (State Machine)   │ │
│  └─────────┘    │ (Chroma) │    └────────────────────┘ │
│                 └──────────┘             │              │
│  ┌─────────────────────────────────────▼──────────────┐│
│  │            FastAPI Backend (Async Streaming)        ││
│  └─────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────┐│
│  │              React Frontend (Tailwind)               ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+ / FastAPI |
| Orchestration | LangGraph 0.2+ |
| Vector Store | ChromaDB (local) |
| LLM | Claude claude-sonnet-4-6 via Anthropic SDK |
| Document Parsing | LlamaParse / python-docx / PyMuPDF |
| Frontend | React 18 + Tailwind CSS |
| Export | python-docx / markdown |

## Quick Start

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Add your ANTHROPIC_API_KEY
uvicorn api.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                   # Runs on http://localhost:5173
```

## Project Structure

```
docuforge/
├── backend/
│   ├── api/
│   │   ├── main.py           # FastAPI app + routes
│   │   └── schemas.py        # Pydantic request/response models
│   ├── core/
│   │   ├── config.py         # Settings & env vars
│   │   └── prompts.py        # All LLM prompt templates
│   ├── ingestion/
│   │   ├── parser.py         # Document parsing (PDF/DOCX/MD)
│   │   ├── chunker.py        # Parent-child hierarchical chunking
│   │   └── embedder.py       # Embedding + Chroma upsert
│   ├── graph/
│   │   ├── state.py          # LangGraph state schema
│   │   ├── nodes.py          # All graph node functions
│   │   └── builder.py        # Graph assembly & compilation
│   └── utils/
│       ├── exporter.py       # Markdown → DOCX export
│       └── logger.py         # Structured logging
├── frontend/
│   └── src/
│       ├── components/       # Reusable UI components
│       ├── pages/            # Upload, Generate, Preview pages
│       ├── hooks/            # useGeneration, useUpload hooks
│       └── lib/              # API client
└── docs/                     # Sample reference documents
```

## Document Generation Flow

1. **Upload** your reference docs (PDF, DOCX, MD, TXT)
2. **Select** target artifact: BRD / FSD / TSD
3. **DocuForge** runs the agentic loop:
   - Plans a full TOC for the chosen artifact type
   - Retrieves context per section from the vector store
   - Drafts each section independently
   - Self-critiques against source docs
   - Re-drafts on failure (up to 3 retries per section)
4. **Export** the compiled document as Markdown or DOCX

## Deployment

### Docker (backend)

```bash
docker compose up -d --build
```

Single container — no Redis/Postgres/separate services required. `docker-compose.yml`
mounts one named volume (`docuforge_data`) for both the Chroma vector store and the
SQLite job store, so data survives container restarts and redeploys. The image bakes
Chroma's embedding model in at build time, so a freshly-built container has no cold-start
delay on its first request.

The frontend isn't containerized yet — run it separately (`cd frontend && npm run dev`,
or `npm run build` + serve the static output behind any web server) and point
`VITE_API_URL` at wherever the backend container is reachable.

### Secrets management

Locally, `backend/.env` (never committed — see `.gitignore`) is enough. For anything
beyond your own machine:

- **Don't bake secrets into the Docker image.** `backend/.dockerignore` already excludes
  `.env`; keep it that way. `docker-compose.yml` reads `env_file: ./backend/.env` from the
  *host* at container start — that file only needs to exist on whatever machine runs
  `docker compose up`, never inside the image or a git commit.
- **On a PaaS (Fly.io, Railway, Render, a VPS, etc.), use that platform's own environment
  variable / secrets feature** (its dashboard or CLI) instead of shipping a `.env` file to
  the server. This needs no extra service or library — consistent with this project's
  preference for the fewest moving parts (see `CLAUDE.md`'s architecture principle) — and
  every mainstream host already provides it.
- **Reach for a dedicated secrets manager (AWS Secrets Manager, GCP Secret Manager,
  HashiCorp Vault, etc.) only if you have a real reason to** — multiple services sharing
  credentials, compliance requirements, or secret rotation automation. For DocuForge's
  current single-container shape, that's very likely more infrastructure than the problem
  needs.
- **If a key leaks** (committed by accident, pasted somewhere public): rotate it
  immediately in the Anthropic console, update wherever it's stored for deployment, and
  restart the backend. Rotating doesn't require any code change — `ANTHROPIC_API_KEY` is
  read fresh from the environment at process startup (`backend/core/config.py`).
- **CI needs no real secrets.** `backend/tests/conftest.py` supplies a dummy
  `ANTHROPIC_API_KEY` so the whole test suite runs offline — don't add a real key as a CI
  secret unless a future change genuinely needs to call the live API in a test.
