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
