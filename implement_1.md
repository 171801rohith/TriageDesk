# TriageDesk — Implementation Plan

> Build order for the system in `requirements.md` / `architecture.md`.
> Each phase has: **Goal → Files → What to write → Checkpoint → Explain it.**
> Don't start a phase until the previous checkpoint passes and you can answer its "Explain it" questions out loud.

**How to use this without blindly copying code**

- Code blocks here are **skeletons** for the parts where the exact library API matters (so you don't waste time on wrong imports). Bodies marked `# TODO` are yours to write.
- Before writing a file, write 2–3 comment lines at the top saying what it does. If you can't, reread the architecture section first.
- If you use an AI assistant, ask it to **review** code you wrote, or to explain one function — not to write a whole module.
- Commit after each phase with a message describing *what you learned*, e.g. `phase 3: chunk + embed + pgvector search`.

Versions checked on PyPI / official docs (Sept 2026): `langchain` 1.4, `langchain-core` 1.6, `langchain-google-genai` 4.4, `langchain-ollama` 1.1, `langchain-text-splitters` 1.1, `fastapi` 0.141, `sqlalchemy` 2.0, `psycopg` 3.3, `pgvector` 0.5, `alembic` 1.20, `pydantic-settings` 2.15. Pin major versions; these libraries move fast.

---

## Phase 0 — Setup (½ day)

**Goal:** Empty project runs; Postgres with pgvector is up; at least one LLM provider answers.

**Prerequisites:** Python 3.12, Docker, (optional) Ollama installed locally, (optional) a Gemini API key from Google AI Studio.

**`pyproject.toml` dependencies**

```toml
[project]
name = "triagedesk"
requires-python = ">=3.12"
dependencies = [
  "fastapi[standard]>=0.141",     # includes uvicorn
  "sqlalchemy>=2.0,<2.1",
  "psycopg[binary]>=3.3",
  "pgvector>=0.5",
  "alembic>=1.20",
  "pydantic-settings>=2.15",
  "langchain-core>=1.6,<2",
  "langchain-text-splitters>=1.1,<2",
  "langchain-google-genai>=4.4,<5",
  "langchain-ollama>=1.1,<2",
]
[project.optional-dependencies]
dev = ["pytest>=9", "httpx>=0.28", "ruff"]
```

Note you don't need the `langchain` meta-package — everything used lives in `langchain-core` + the integration packages. Fewer deps = fewer things to explain.

**`docker-compose.yml` (db only for now)**

```yaml
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: triage
      POSTGRES_PASSWORD: triage
      POSTGRES_DB: triagedesk
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
volumes:
  pgdata:
```

**Ollama (if using):**
```bash
ollama pull llama3.1:8b          # or qwen3:8b — needs to support tool/JSON output
ollama pull nomic-embed-text     # 768-dim embeddings
```

**Checkpoint**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d db
python -c "from langchain_ollama import ChatOllama; print(ChatOllama(model='llama3.1:8b').invoke('Say hi').content)"
# or
python -c "from langchain_google_genai import ChatGoogleGenerativeAI as C; print(C(model='gemini-3.7-flash').invoke('Say hi').content)"
```
(Check https://ai.google.dev/gemini-api/docs/models for current Gemini model IDs; they change often.)

**Explain it:** What does `.invoke()` return? (An `AIMessage` — look at `.content` and `.usage_metadata`.)

---

## Phase 1 — FastAPI skeleton + config (½ day)

**Goal:** App starts, `/api/v1/health` returns the active provider.

**Files:** `app/main.py`, `app/core/config.py`, `app/health/router.py`, `.env.example`

**What to write**

`core/config.py` — one `Settings(BaseSettings)` class with every variable from `architecture.md` §7. Use `Literal["gemini", "ollama"]` for `llm_provider` so a typo fails at startup. Expose `get_settings()` decorated with `@lru_cache`.

```python
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    llm_provider: Literal["gemini", "ollama"] = "ollama"
    # TODO: the remaining fields from architecture.md §7

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`main.py` — create `FastAPI(title="TriageDesk")`, include routers with `prefix="/api/v1"`.

**Checkpoint:** `fastapi dev app/main.py` → open `http://localhost:8000/docs`, call `/api/v1/health`.

**Explain it:** Why `@lru_cache` on `get_settings`? What happens if `LLM_PROVIDER=openai`?

---

## Phase 2 — Database layer + migrations (1 day)

**Goal:** All four tables exist via Alembic, including the vector column and HNSW index.

**Files:** `app/core/db.py`, `app/kb/models.py`, `app/tickets/models.py`, `alembic/` (via `alembic init alembic`)

**What to write**

`core/db.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): ...

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Models — use SQLAlchemy 2.0 style (`Mapped[...]`, `mapped_column`). The vector column:
```python
from pgvector.sqlalchemy import Vector
embedding: Mapped[list[float]] = mapped_column(Vector(768))
```
HNSW index (declare in `__table_args__` of `KbChunk`):
```python
Index("ix_kb_chunks_embedding_hnsw", "embedding",
      postgresql_using="hnsw",
      postgresql_with={"m": 16, "ef_construction": 64},
      postgresql_ops={"embedding": "vector_cosine_ops"})
```
JSONB columns: `from sqlalchemy.dialects.postgresql import JSONB`.
CHECK constraints for status/category/priority: `CheckConstraint("status IN ('pending', ...)")`.

Alembic:
1. In `alembic/env.py`, set `target_metadata = Base.metadata` and read the URL from `get_settings()`. Import all model modules so autogenerate sees them.
2. `alembic revision --autogenerate -m "initial"`.
3. **Edit the generated file by hand:** add `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` as the first line of `upgrade()`, and `import pgvector` at the top (autogenerate references `pgvector.sqlalchemy.Vector`).
4. `alembic upgrade head`.

**Checkpoint**
```bash
docker compose exec db psql -U triage -d triagedesk -c "\d kb_chunks"
# embedding | vector(768) and the hnsw index should be listed
```

**Explain it:** Why migrations instead of `Base.metadata.create_all()`? What does `vector_cosine_ops` change? Why is the session closed in `finally`?

---

## Phase 3 — LLM provider factory (½ day)

**Goal:** One function returns a chat model, one returns embeddings, based on config.

**File:** `app/llm/providers.py`

```python
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=s.gemini_chat_model, temperature=temperature,
            timeout=s.llm_timeout_seconds, max_retries=2,
        )  # reads GOOGLE_API_KEY from env
    from langchain_ollama import ChatOllama
    return ChatOllama(model=s.ollama_chat_model, base_url=s.ollama_base_url,
                      temperature=temperature)
    # TODO: how will you enforce a timeout for Ollama? (look at client_kwargs)

def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.llm_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=s.gemini_embed_model, output_dimensionality=s.embedding_dim)
    from langchain_ollama import OllamaEmbeddings
    return OllamaEmbeddings(model=s.ollama_embed_model, base_url=s.ollama_base_url)

def active_model_info() -> dict: ...  # TODO: provider, chat_model, embed_model — used by /health and triage_runs
```

Imports are inside the branches so the unused provider's package isn't loaded. Update `/health` to include `active_model_info()` and a `SELECT 1` DB check.

**Checkpoint:** In a Python shell, `len(get_embeddings().embed_query("hello")) == 768` for **both** providers.

**Explain it:** What do `BaseChatModel` and `Embeddings` give you? What must happen to stored vectors when you switch embedding provider, and why?

---

## Phase 4 — Knowledge base module (1–1½ days)

**Goal:** Add articles → chunked, embedded, searchable.

**Files:** `app/kb/schemas.py`, `app/kb/service.py`, `app/kb/router.py`, `scripts/seed_kb.py`, `data/kb_articles/*.md`

**What to write**

1. **Schemas:** `ArticleIn(title, category, content)`, `ArticleOut`, `SearchIn(query, k=4)`, `SearchHit(chunk_id, article_id, title, text, distance)`. Use `model_config = ConfigDict(from_attributes=True)` on output models.
2. **`service.create_article(db, data, embeddings)`**
   - `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100).split_text(content)` (from `langchain_text_splitters`)
   - `embeddings.embed_documents(chunks)` — **one call for all chunks**
   - add article + chunks, `db.commit()` once
3. **`service.search(db, query, k, embeddings) -> list[SearchHit]`**
   ```python
   q = embeddings.embed_query(query)
   distance = KbChunk.embedding.cosine_distance(q).label("distance")
   stmt = (select(KbChunk, KbArticle.title, distance)
           .join(KbArticle)
           .where(KbChunk.embedding_model == current_embed_model)
           .order_by(distance).limit(k))
   ```
4. **`service.reindex(db, embeddings)`** — re-embed every chunk in batches of ~50, update `embedding` and `embedding_model`.
5. **Router:** endpoints from requirements §5. Inject embeddings with a dependency (`def get_embeddings_dep(): return get_embeddings()`), so tests can override it.
6. **Data:** write ~10 short, realistic articles yourself (refund policy, duplicate charges, password reset, 2FA, shipping times, lost package, app crash troubleshooting, cancel subscription, change email, data export). Writing them helps you design good test tickets later.
7. **`scripts/seed_kb.py`** — reads `data/kb_articles/*.md`, calls `create_article`. First line of each file = title, second = category.

**Checkpoint:** Seed, then `POST /kb/search {"query": "I was billed two times"}` → duplicate-charge article first. Try 5 queries of your own and look at the distances; use them to choose `RETRIEVAL_MAX_DISTANCE`.

**Explain it:** Why chunk at all? What does overlap buy you? What does a distance of 0.2 vs 0.7 mean? Why `embed_documents` vs `embed_query`?

---

## Phase 5 — Triage workflow (2 days) ← the core

**Goal:** A pure-Python workflow that takes a ticket and returns a `TriageResult`, testable without DB or network.

**Files:** `app/triage/llm_schemas.py`, `prompts.py`, `guardrails.py`, `workflow.py`

### 5a. `llm_schemas.py`
Copy the two models from `architecture.md` §5.3. Also define `TriageResult(status, reasons, classification, draft, retrieved, step_timings, error)`. For retrieved chunks, reuse `kb.schemas.SearchHit` (the architecture calls it `RetrievedChunk`; `from app.kb.schemas import SearchHit as RetrievedChunk` keeps one definition — `triage → kb` is an allowed dependency).

### 5b. `guardrails.py` — write this **first**, with tests
```python
def evaluate(classification: Classification,
             draft: DraftReply | None,
             retrieved: list[RetrievedChunk],
             confidence_threshold: float) -> tuple[str, list[str]]:
    reasons: list[str] = []
    # TODO: one `if` per rule in requirements FR-12; append a reason code each time
    #   "urgent_priority", "negative_high_priority", "low_confidence",
    #   "unknown_citation", "empty_reply", "no_relevant_kb"
    return ("needs_review" if reasons else "auto_ready"), reasons
```
Write `tests/unit/test_guardrails.py` now: one test per rule + one "all clear" test. No LLM involved — this should take an hour and pass 100%.

### 5c. `prompts.py`
```python
from langchain_core.prompts import ChatPromptTemplate
PROMPT_VERSION = "v1"

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a support triage assistant. Classify the ticket. "
               "Use 'urgent' only for outages, security issues, or data loss."),
    ("human", "Subject: {subject}\n\nBody:\n{body}"),
])

DRAFT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You write replies for a support team. Use ONLY the passages below. "
               "Cite the article ids you used. If the passages don't answer the "
               "question, say what's missing and give low confidence.\n\n{passages}"),
    ("human", "Category: {category}\nSubject: {subject}\n\n{body}"),
])
```
Write your own wording — these are starting points. Format `passages` as `[article_id=3] Title\n<text>` blocks so the model can cite ids.

### 5d. `workflow.py`
Build chains in a small factory, and make the workflow take them as arguments (this is what makes it testable):

```python
from langchain_core.runnables import Runnable

def build_classifier(chat_model) -> Runnable:
    return CLASSIFY_PROMPT | chat_model.with_structured_output(Classification, method="json_schema")

def build_drafter(chat_model) -> Runnable:
    return DRAFT_PROMPT | chat_model.with_structured_output(DraftReply, method="json_schema")

class TriageWorkflow:
    def __init__(self, classifier: Runnable, drafter: Runnable,
                 search_fn: Callable[[str], list[RetrievedChunk]], settings: Settings): ...

    def run(self, subject: str, body: str) -> TriageResult:
        timings = {}
        try:
            # 1. classification = self.classifier.invoke({"subject": ..., "body": ...})  (time it)
            # 2. retrieved = [c for c in self.search_fn(subject + "\n" + body)
            #                 if c.distance <= settings.retrieval_max_distance]
            # 3. if retrieved: draft = self.drafter.invoke({...passages...}) else draft = None
            # 4. status, reasons = guardrails.evaluate(...)
            ...
        except Exception as e:
            # TODO: log it; return TriageResult(status="needs_review", reasons=["llm_error"], error=str(e), ...)
            ...
```

Notes:
- `with_structured_output(..., method="json_schema")` is supported by both `ChatGoogleGenerativeAI` and `ChatOllama`. Small local models sometimes return invalid JSON — that raises, your `except` routes the ticket to review. For debugging, try `include_raw=True` to see the raw message alongside the parsed one.
- Use `time.perf_counter()` for step timings.
- Classifier uses `get_chat_model(temperature=0)`, drafter `get_chat_model(temperature=0.2)`.

**Checkpoint:** A throwaway script builds the real workflow with your provider and runs it on 3 tickets (billing, urgent outage, off-topic). Print the `TriageResult`. Then `tests/unit/test_workflow.py` passes using fakes (see Phase 8).

**Explain it:** What does `prompt | model` create? What exactly does `with_structured_output` send to the model and do with the response? Why are guardrails not in the prompt? What happens when the model returns `priority: "critical"`?

---

## Phase 6 — Tickets module + persistence (1–1½ days)

**Goal:** API endpoints that create tickets, run the workflow, store runs, and handle review.

**Files:** `app/tickets/schemas.py`, `service.py`, `router.py`

**What to write**

1. **Schemas:** `TicketIn` (`customer_email: EmailStr`, `subject` 1–200 chars, `body` 1–10 000 chars), `TicketOut` (fields from requirements §5 example), `ReviewIn(action: Literal["approve","edit","reject"], final_reply: str | None, note: str | None)` with a validator: `edit` requires `final_reply`.
2. **Workflow dependency** in `router.py`:
   ```python
   def get_workflow(db: Session = Depends(get_db)) -> TriageWorkflow:
       emb = get_embeddings()
       return TriageWorkflow(
           classifier=build_classifier(get_chat_model(0)),
           drafter=build_drafter(get_chat_model(0.2)),
           search_fn=lambda q: kb_service.search(db, q, get_settings().retrieval_k, emb),
           settings=get_settings())
   ```
   Tests override this with `app.dependency_overrides[get_workflow] = ...`.
3. **`service.create_ticket(db, data, workflow)`**: insert ticket (`pending`) → `db.flush()` to get the id → `_apply_triage(db, ticket, workflow)` → commit.
4. **`_apply_triage`**: call `workflow.run`, insert a `TriageRun` (with `active_model_info()`, `PROMPT_VERSION`, `model_dump()` of outputs, timings, error), copy latest results onto the ticket. Shared by create and re-triage.
5. **`service.review(db, ticket_id, review)`**: 404 if missing, 409 if status not in {`auto_ready`, `needs_review`}, then apply the action and set `reviewed_at`. Raise small custom exceptions (`NotFound`, `Conflict`) in the service and map them to HTTP codes in `main.py` exception handlers — keeps HTTP out of services.
6. **List + stats:** filters with `limit`/`offset`; `/stats` uses `GROUP BY` queries (`select(Ticket.status, func.count()).group_by(Ticket.status)`), plus `avg(latency_ms)` grouped by provider from `triage_runs`.

**Checkpoint:** Walk through acceptance criteria 3–7 in Swagger UI.

**Explain it:** Why `flush()` before the workflow? What happens to the ticket if the process crashes mid-triage? (It stays `pending` — a "re-run" button fixes it. Good trade-off to mention.) Why do services raise custom exceptions rather than `HTTPException`?

---

## Phase 7 — Provider switch + evaluation (1 day)

**Goal:** Prove the switch works and measure quality instead of guessing.

**Files:** `data/eval_tickets.jsonl`, `scripts/eval_triage.py`

1. Write ≥ 20 tickets yourself with expected labels: `{"subject": ..., "body": ..., "category": "billing", "priority": "medium"}`. Include tricky ones (angry but low priority, polite but urgent, two issues in one ticket).
2. `eval_triage.py` builds the classifier via the factory, runs every ticket, prints accuracy per field, a confusion list of mistakes, and average latency. No DB needed.
3. Run with `LLM_PROVIDER=gemini`, then `ollama` (after `POST /kb/reindex`). Save the numbers in the README.
4. Change one prompt line, bump `PROMPT_VERSION`, re-run. Note the difference.

**Checkpoint:** A small results table in the README: provider | model | category acc | priority acc | avg latency.

**Explain it:** Why is an eval set better than "it looked good on 3 examples"? What would you change if priority accuracy is low?

> Only put numbers on your resume that this script actually produced.

---

## Phase 8 — Testing (spread across phases; 1 day to finish)

**Files:** `tests/conftest.py`, `tests/unit/*`, `tests/integration/test_api.py`

**Unit tests (no network, no DB)**
- `test_guardrails.py` — every rule (Phase 5b).
- `test_workflow.py` — use `RunnableLambda` as a fake chain:
  ```python
  from langchain_core.runnables import RunnableLambda
  fake_classifier = RunnableLambda(lambda _: Classification(category="billing", priority="urgent", ...))
  failing = RunnableLambda(lambda _: (_ for _ in ()).throw(TimeoutError("boom")))
  ```
  Cases: happy path → `auto_ready`; urgent → `needs_review`; empty search → draft not called + `no_relevant_kb`; classifier raises → `llm_error`; citation not in retrieved → `unknown_citation`.
- `test_chunking.py` — long text → multiple chunks, each ≤ 800 chars.

**Integration tests (real Postgres, fake LLM)**
- Create a separate DB `triagedesk_test`, run `alembic upgrade head` against it once per session in `conftest.py`.
- Wrap each test in a transaction and roll back at the end (or truncate tables).
- Fake embeddings: `from langchain_core.embeddings import DeterministicFakeEmbedding; DeterministicFakeEmbedding(size=768)` — override the embeddings dependency.
- Override `get_workflow` with a workflow built from `RunnableLambda` fakes.
- Use FastAPI's `TestClient`. Cover: create ticket 201, get 404, review edit → approved, double review → 409, KB create + delete cascade.

**Checkpoint:** `pytest -q` green with no `GOOGLE_API_KEY` set and Ollama stopped.

**Explain it:** Why can the workflow be tested without a real LLM? What *can't* these tests catch? (Prompt quality — that's what the eval script is for.)

---

## Phase 9 — Docker + README (½ day)

**`Dockerfile`**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic ./alembic
COPY alembic.ini .
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

Add to `docker-compose.yml`:
```yaml
  api:
    build: .
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://triage:triage@db:5432/triagedesk
      OLLAMA_BASE_URL: http://host.docker.internal:11434
    extra_hosts: ["host.docker.internal:host-gateway"]   # needed on Linux
    ports: ["8000:8000"]
    depends_on: [db]
```
Ollama stays on the host (it needs your GPU/RAM; containerising it adds nothing here).

**README sections:** what it does (3 lines) · architecture diagram (copy from `architecture.md`) · quickstart · switching providers · design decisions (copy §3) · eval results · what you'd add next.

**Checkpoint:** Fresh clone → `cp .env.example .env` → `docker compose up --build` → seed → create a ticket. Works.

---

## Summary: build order and rough time

| Phase | What | Days |
|-------|------|------|
| 0 | Setup, verify providers | 0.5 |
| 1 | FastAPI + config | 0.5 |
| 2 | DB models + Alembic + pgvector | 1 |
| 3 | Provider factory | 0.5 |
| 4 | KB: chunk, embed, search | 1–1.5 |
| 5 | Triage workflow + guardrails | 2 |
| 6 | Tickets API + persistence + review | 1–1.5 |
| 7 | Provider switch + eval | 1 |
| 8 | Tests | 1 |
| 9 | Docker + README | 0.5 |
| | **Total** | **~9–10 days part-time-ish** |

## Stretch goals (only after everything above works)
1. Move triage to `BackgroundTasks` and return 202 with the ticket id.
2. Rewrite `workflow.py` as a LangGraph `StateGraph` with 4 nodes and one conditional edge — compare readability honestly.
3. Add one tool for shipping tickets (`get_order_status(order_id)` against a fake orders table) called only when `category == "shipping"`.
4. Hybrid search (Postgres full-text + vector) and compare retrieval on your eval set.
5. API-key auth on review endpoints.

## Resume bullet template (fill with your real numbers)
- Built **TriageDesk**, a FastAPI + PostgreSQL/pgvector service that classifies support tickets, retrieves relevant KB passages, and drafts cited replies using LangChain structured output, with deterministic guardrails routing risky cases to human review.
- Designed a provider-agnostic LLM layer supporting **Gemini** and local **Ollama** via config; evaluated both on a labelled set (**X%** vs **Y%** category accuracy, **A s** vs **B s** avg latency).
- Logged every LLM run (model, prompt version, per-step latency, errors) for auditability; **N** unit/integration tests run fully offline using fake LLMs and embeddings.
