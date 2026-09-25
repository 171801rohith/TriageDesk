# TriageDesk — Requirements

> AI-assisted support-ticket triage API.
> Stack: Python 3.12 · FastAPI · PostgreSQL + pgvector · SQLAlchemy 2 · Alembic · LangChain 1.x · Gemini **or** Ollama.
> Companion docs: `architecture.md` (how it's built), `implement.md` (build order).

---

## 1. Problem

Small support teams get a steady stream of tickets ("I was charged twice", "the app crashes on login", "where is my order?"). A human has to read each one, decide what it's about and how urgent it is, dig up the right help-center article, and write a reply. Most of that is repetitive; the risky part is sending a wrong or made-up answer to a customer.

**TriageDesk** automates the repetitive part and keeps a human in charge of the risky part:

1. **Classifies** each ticket (category, priority, sentiment, one-line summary) using an LLM with **structured output**.
2. **Retrieves** the most relevant knowledge-base (KB) passages from PostgreSQL using **vector search**.
3. **Drafts** a reply grounded only in those passages, with citations and a confidence score.
4. Applies **deterministic guardrails** (plain Python rules) that decide whether the draft is `auto_ready` or must go to `needs_review`.
5. Lets a human **approve, edit, or reject** the draft. Nothing is ever sent to a customer automatically.

Every LLM run is logged (provider, model, latency, outputs, errors) so results are auditable and the two providers (Gemini vs Ollama) can be compared.

---

## 2. Features

| # | Feature | Short description |
|---|---------|-------------------|
| F1 | KB article management | Add/list/delete help articles. On add, the article is split into chunks, embedded, and stored in pgvector. |
| F2 | KB semantic search | Search the KB with a natural-language query (useful on its own and for debugging retrieval). |
| F3 | Ticket intake | Create a ticket (customer email, subject, body). Triage runs immediately. |
| F4 | Triage workflow | Fixed 4-step pipeline: classify → retrieve → draft → guardrails. |
| F5 | Human review queue | List tickets needing review; approve / edit / reject a draft. |
| F6 | Re-run triage | Re-run the workflow on a ticket (e.g., after adding KB articles or switching provider). |
| F7 | Run audit log | Each triage run is stored with provider, model, timings, raw structured outputs, and error (if any). |
| F8 | Switchable LLM provider | `LLM_PROVIDER=gemini` or `ollama` in `.env`; no code changes. |
| F9 | Stats + evaluation script | `/stats` endpoint (counts by status/category) and a small offline eval script that measures classification accuracy on a labelled sample set. |

---

## 3. Functional requirements

### Knowledge base
- **FR-1** The system shall accept a KB article with `title`, `category`, and `content` (plain text/markdown).
- **FR-2** On creation, the system shall split content into chunks (target ~800 characters, ~100 overlap), embed each chunk, and store chunks with their embedding and the embedding model name.
- **FR-3** Deleting an article shall delete its chunks (cascade).
- **FR-4** KB search shall return the top-k chunks (default k=4) ordered by cosine distance, each with `article_id`, `title`, `chunk_text`, `distance`.
- **FR-5** Search shall only compare against chunks produced by the **currently configured** embedding model (embeddings from different models are not comparable).
- **FR-6** A reindex endpoint shall re-embed all chunks with the current embedding model.

### Tickets and triage
- **FR-7** Creating a ticket shall persist it with status `pending`, then run the triage workflow synchronously and return the ticket with its triage result.
- **FR-8** **Classify step** shall return a validated object: `category` ∈ {billing, technical, account, shipping, other}, `priority` ∈ {low, medium, high, urgent}, `sentiment` ∈ {positive, neutral, negative}, `summary` (≤ 200 chars), `language` (ISO code).
- **FR-9** **Retrieve step** shall run vector search using `subject + body` as the query and keep only chunks with distance ≤ `RETRIEVAL_MAX_DISTANCE` (configurable, default 0.5).
- **FR-10** **Draft step** shall return: `reply` (text), `cited_article_ids` (list of ints), `confidence` (0.0–1.0), `missing_info` (optional string). The prompt shall instruct the model to use only the provided passages.
- **FR-11** If no chunk passes the distance threshold, the draft step shall be **skipped** and the ticket marked `needs_review` with reason `no_relevant_kb`.
- **FR-12** **Guardrails step** (pure Python, no LLM) shall set status to `needs_review` if ANY of:
  - priority is `urgent`
  - sentiment is `negative` **and** priority is `high`
  - `confidence < CONFIDENCE_THRESHOLD` (default 0.7)
  - any `cited_article_ids` value is not among the retrieved articles (possible hallucinated citation)
  - reply is empty or the draft cites nothing
  Otherwise status is `auto_ready`. All triggered reasons are stored as a list.
- **FR-13** If any LLM call fails (timeout, API error, invalid structured output after retries), the ticket shall be saved with status `needs_review`, and the run stored with `status=failed` and the error message. The API must not return 500 for an LLM failure.
- **FR-14** Each workflow execution shall create one `triage_runs` row.
- **FR-15** `POST /tickets/{id}/triage` shall re-run the workflow and create a new run; the ticket shows the latest run.

### Review
- **FR-16** `GET /tickets?status=needs_review` shall list tickets for review (newest first, paginated with `limit`/`offset`).
- **FR-17** `POST /tickets/{id}/review` with `action` ∈ {approve, edit, reject}:
  - `approve` → `final_reply` = draft reply; status `approved`
  - `edit` → requires `final_reply`; status `approved`
  - `reject` → status `rejected`; optional `note`
- **FR-18** Only tickets in `auto_ready` or `needs_review` can be reviewed; otherwise return 409.

### Provider switching
- **FR-19** The chat model and embedding model shall be created by one factory module, based on `LLM_PROVIDER` and model-name settings.
- **FR-20** `GET /health` shall report DB connectivity and the active provider + model names.

---

## 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR-1 **Simplicity** | Single FastAPI service + one PostgreSQL database. No queues, caches, or extra services. |
| NFR-2 **Modularity** | Code is organised by feature (`kb`, `tickets`, `triage`, `llm`). Routers contain no business logic; LangChain code lives only in `llm/` and `triage/`. |
| NFR-3 **Determinism where it matters** | The step order is fixed in code. Business decisions (status, review rules) are plain Python, never left to the LLM. `temperature=0` for classification. |
| NFR-4 **Reliability** | LLM calls have a timeout (`LLM_TIMEOUT_SECONDS`, default 60) and `max_retries=2`. Failures degrade to `needs_review`. |
| NFR-5 **Observability** | Structured logs per request; per-step latency stored in `triage_runs.step_timings`. |
| NFR-6 **Security** | API keys only from environment variables; never logged or stored. Customer text is sent only to the configured provider (Ollama keeps data local). |
| NFR-7 **Testability** | LLM and embeddings are injected, so unit tests run with fakes and no network. |
| NFR-8 **Performance (target, not SLA)** | Triage of one ticket < 15 s with Gemini; Ollama depends on hardware. KB search < 200 ms for ≤ 10k chunks. |
| NFR-9 **Portability** | `docker compose up` starts Postgres (pgvector) and the API. Ollama runs on the host. |

---

## 5. API

Base path: `/api/v1`. JSON in/out. Pydantic validates all request bodies (422 on invalid input).

| Method | Path | Purpose | Success |
|--------|------|---------|---------|
| GET | `/health` | DB status, provider, model names | 200 |
| POST | `/kb/articles` | Create article (chunk + embed) | 201 |
| GET | `/kb/articles` | List articles (`limit`, `offset`) | 200 |
| GET | `/kb/articles/{id}` | Get article | 200 / 404 |
| DELETE | `/kb/articles/{id}` | Delete article + chunks | 204 / 404 |
| POST | `/kb/search` | Semantic search `{query, k}` | 200 |
| POST | `/kb/reindex` | Re-embed all chunks with current model | 200 |
| POST | `/tickets` | Create ticket + run triage | 201 |
| GET | `/tickets` | List (`status`, `category`, `limit`, `offset`) | 200 |
| GET | `/tickets/{id}` | Ticket + latest triage result | 200 / 404 |
| POST | `/tickets/{id}/triage` | Re-run triage | 200 / 404 |
| POST | `/tickets/{id}/review` | Approve / edit / reject | 200 / 404 / 409 |
| GET | `/tickets/{id}/runs` | All triage runs for a ticket | 200 / 404 |
| GET | `/stats` | Counts by status, category, provider; avg latency | 200 |

### Example: create ticket

Request
```json
POST /api/v1/tickets
{
  "customer_email": "sam@example.com",
  "subject": "Charged twice this month",
  "body": "Hi, my card was charged twice for the Pro plan on Sept 3. Please refund one."
}
```

Response `201`
```json
{
  "id": 42,
  "status": "auto_ready",
  "subject": "Charged twice this month",
  "classification": {
    "category": "billing",
    "priority": "medium",
    "sentiment": "negative",
    "summary": "Customer reports duplicate Pro plan charge and requests refund.",
    "language": "en"
  },
  "draft_reply": "Hi Sam, sorry about the duplicate charge...",
  "cited_article_ids": [3],
  "confidence": 0.86,
  "review_reasons": [],
  "latest_run": { "id": 57, "provider": "gemini", "model": "gemini-3.7-flash", "latency_ms": 4120, "status": "succeeded" }
}
```

### Example: review

```json
POST /api/v1/tickets/42/review
{ "action": "edit", "final_reply": "Hi Sam, we've refunded the duplicate charge..." }
```

### Error format
```json
{ "detail": "Ticket 42 cannot be reviewed in status 'approved'" }
```

---

## 6. Database requirements

- PostgreSQL 16+ with the **pgvector** extension (`CREATE EXTENSION IF NOT EXISTS vector`).
- Schema managed by **Alembic** migrations only (no `create_all` in production code).
- Tables: `kb_articles`, `kb_chunks`, `tickets`, `triage_runs` (full design in `architecture.md` §6).
- Embedding column: `vector(768)` — both chosen embedding models output 768 dimensions (Gemini via `output_dimensionality=768`, Ollama `nomic-embed-text` natively).
- HNSW index on `kb_chunks.embedding` with `vector_cosine_ops`.
- Enum-like columns (`status`, `category`, `priority`) stored as `VARCHAR` + CHECK constraint (simpler to migrate than native PG enums).
- LLM outputs stored as `JSONB` in `triage_runs` for auditing.
- All tables have `created_at` (timestamptz, default now()).

## 7. LLM requirements

| Item | Gemini | Ollama |
|------|--------|--------|
| LangChain package | `langchain-google-genai` (4.x, uses the unified `google-genai` SDK) | `langchain-ollama` (1.x) |
| Chat class | `ChatGoogleGenerativeAI` | `ChatOllama` |
| Default chat model (configurable) | `gemini-3.7-flash` (check the Gemini models page for current IDs) | `llama3.1:8b` or `qwen3:8b` |
| Embedding class | `GoogleGenerativeAIEmbeddings` | `OllamaEmbeddings` |
| Embedding model | `gemini-embedding-001`, `output_dimensionality=768` | `nomic-embed-text` (768-d) |
| Auth | `GOOGLE_API_KEY` env var | none (local server at `OLLAMA_BASE_URL`, default `http://localhost:11434`) |

- Both steps that call the LLM use **`with_structured_output(PydanticModel, method="json_schema")`** so the result is a validated Pydantic object, not free text to parse.
- Prompts live in one module (`triage/prompts.py`) as `ChatPromptTemplate`s and carry a `PROMPT_VERSION` string stored with each run.
- Classification uses `temperature=0`; drafting may use `0.2–0.3`.
- Switching **chat** provider needs no data changes. Switching **embedding** provider requires `POST /kb/reindex` (see FR-5/FR-6).

---

## 8. Out of scope

- Sending emails or integrating with real helpdesks (Zendesk, Freshdesk, etc.).
- Authentication/authorization and multi-tenant support (a single internal user is assumed; can be added later).
- Frontend UI (use Swagger UI at `/docs`).
- File uploads / PDF parsing for KB (plain text only).
- Autonomous agents, multi-agent systems, LangGraph (the flow is linear; see `architecture.md` §5.4 for why).
- Background workers, Redis, Kafka, Celery, Kubernetes, microservices.
- Streaming responses, conversation memory, chat with the KB.
- Fine-tuning or training models.

---

## 9. Acceptance criteria

1. **Setup**: `docker compose up -d db` + `alembic upgrade head` + `uvicorn app.main:app` starts the app; `GET /api/v1/health` returns `{"db": "ok", "provider": "...", ...}`.
2. **KB**: After running `scripts/seed_kb.py` (≈10 sample articles), `POST /kb/search {"query": "refund duplicate charge"}` returns a billing article as the top result.
3. **Happy path**: Creating the "charged twice" ticket returns 201 with `category=billing`, a non-empty draft reply that cites at least one retrieved article, and a `triage_runs` row with `status=succeeded` and per-step timings.
4. **Guardrails**: A ticket containing "URGENT: production is down for all users" ends in `needs_review` with `"urgent_priority"` in `review_reasons`.
5. **No KB match**: A ticket about something not in the KB ("Do you sell gift cards in Brazil?") ends in `needs_review` with reason `no_relevant_kb` and no draft.
6. **LLM failure**: With Ollama stopped (or an invalid Gemini key), creating a ticket still returns 201, status `needs_review`, and a run with `status=failed` and an error message.
7. **Review**: `edit` sets `final_reply` and status `approved`; reviewing an already-approved ticket returns 409.
8. **Provider switch**: Changing `LLM_PROVIDER` from `gemini` to `ollama` (and running reindex) and restarting makes new runs show `provider=ollama`, with no code change.
9. **Tests**: `pytest` passes; unit tests run without network or API keys (fake LLM + fake embeddings).
10. **Eval**: `python scripts/eval_triage.py` prints category accuracy and priority accuracy on `data/eval_tickets.jsonl` (≥ 20 labelled tickets) for the active provider.
11. **Explainability**: The author can explain, without notes, every step in `architecture.md` §4 sequence diagram.
