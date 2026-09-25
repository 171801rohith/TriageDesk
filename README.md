# TriageDesk

AI-assisted support-ticket triage API: classifies tickets, retrieves relevant KB passages
with pgvector, drafts cited replies, and routes risky cases to human review via
deterministic guardrails. See `requirements.md`, `architecture.md`, `implement_1.md`.

> Status: scaffold only — most functions raise `NotImplementedError` (served as HTTP 501).

## Architecture

TODO: copy the diagram from `architecture.md` §1.

## Quickstart

```bash
cp .env.example .env              # then fill in GOOGLE_API_KEY or use LLM_PROVIDER=ollama
uv sync --extra dev
docker compose up -d db
uv run alembic revision --autogenerate -m "initial"   # first time only; edit per implement_1.md Phase 2
uv run alembic upgrade head
uv run fastapi dev app/main.py    # http://localhost:8000/docs
uv run python scripts/seed_kb.py
```

## Switching providers

TODO: `LLM_PROVIDER=gemini|ollama`, then `POST /api/v1/kb/reindex` when the embedding model changes.

## Design decisions

TODO: copy `architecture.md` §3.

## Eval results

| provider | model | category acc | priority acc | avg latency |
|----------|-------|--------------|--------------|-------------|
| TODO     |       |              |              |             |

## What I'd add next

TODO: see `architecture.md` §9.
