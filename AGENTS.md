# AGENTS.md

Operating rules for any agent (Claude Code or otherwise) working in this repository.

## Commit policy — always follow this

- After every significant task, or each discrete unit of progress (a completed action item,
  a working fix, a finished file), **stage and commit** the relevant changes with a clear,
  descriptive commit message.
- Do this proactively — don't wait to be asked to commit.
- **Never run `git push`.** Pushing to any remote is the user's action alone. Leave commits
  local and let the user push when they're ready.
- Prefer several small, logically-scoped commits over one large commit at the end of a session.
- Never amend or rewrite existing commits unless explicitly asked.

## What never gets staged

Before every `git add`, confirm none of these are included (check `.gitignore` covers them,
and double-check `git status` output directly):

- `backend/.env` (secrets — `ANTHROPIC_API_KEY`, `LLAMA_CLOUD_API_KEY`)
- `backend/chroma_db/` (local vector store data, not source)
- `frontend/node_modules/`
- Any other credentials, API keys, or generated data files

`frontend/package-lock.json` is source and should be committed normally (it is not covered
by the exclusions above).

## Where to look before starting work

- `CLAUDE.md` — architecture map and how to run the project locally.
- `ROADMAP.md` — phased plan with concrete action items; pick up from the current phase
  instead of re-deriving scope from scratch each session.

## Scope discipline

- Don't add speculative abstractions, config flags, or "future-proofing" beyond what the
  current task/roadmap item calls for.
- Keep documentation (`CLAUDE.md`, `ROADMAP.md`, `README.md`) in sync with what's actually
  implemented — if a roadmap item is completed, update `ROADMAP.md` to reflect it in the same
  commit.
