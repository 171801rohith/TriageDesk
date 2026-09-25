# TriageDesk — Architecture

> Read `requirements.md` first. This doc explains **how** the system is built and **why** each part exists.
> Guiding rule: *the code decides the order of steps and the business rules; the LLM only fills in well-defined boxes.*

---

## 1. Architecture at a glance

**Style:** modular monolith — one FastAPI process, one PostgreSQL database, code split into feature modules with one-way dependencies.

```mermaid
flowchart LR
    Client["Client<br/>(Swagger UI / curl / tests)"] --> API

    subgraph App["FastAPI app (single process)"]
        API["Routers<br/>kb · tickets · health · stats"]
        TS["tickets.service"]
        KS["kb.service<br/>(chunk, embed, search)"]
        WF["triage.workflow<br/>classify → retrieve → draft → guardrails"]
        LLM["llm.providers<br/>(factory)"]
        API --> TS
        API --> KS
        TS --> WF
        WF --> KS
        WF --> LLM
        KS --> LLM
    end

    TS --> PG[("PostgreSQL + pgvector")]
    KS --> PG
    LLM -->|LLM_PROVIDER=gemini| GEM["Gemini API"]
    LLM -->|LLM_PROVIDER=ollama| OLL["Ollama (local)"]
```

**What is deliberately missing:** no message queue, no cache, no worker process, no second service, no agent framework. Each would add something to run and explain without solving a problem this project has (see §9).

---

## 2. Components and why they exist

| Component | Responsibility | Why it exists / why this choice |
|-----------|---------------|--------------------------------|
| `core/config.py` | Load settings from env via `pydantic-settings` | One typed place for every knob (provider, models, thresholds). Makes provider switching a config change. |
| `core/db.py` | SQLAlchemy engine, `SessionLocal`, `get_db()` dependency | FastAPI `Depends(get_db)` gives each request its own session and closes it afterwards. |
| `llm/providers.py` | `get_chat_model(temperature)` and `get_embeddings()` factories | The **only** file that knows about Gemini vs Ollama. Everything else receives a LangChain `BaseChatModel` / `Embeddings`, so switching providers doesn't touch other code. |
| `kb/` (models, schemas, service, router) | Article CRUD, chunking, embedding, vector search | Retrieval is a real feature (also exposed as `/kb/search`), so it gets its own module that `triage` can reuse. |
| `tickets/` (models, schemas, service, router) | Ticket CRUD, review actions, status transitions | Owns the ticket lifecycle. Calls the workflow but doesn't know LLM details. |
| `triage/llm_schemas.py` | Pydantic models the LLM must fill (`Classification`, `DraftReply`) | These are the "contract" with the LLM. Validation happens automatically. |
| `triage/prompts.py` | `ChatPromptTemplate`s + `PROMPT_VERSION` | Keeps prompts reviewable and versioned in one place. |
| `triage/workflow.py` | Runs the 4 steps in order, times them, returns a `TriageResult` | Explicit, readable pipeline — you can point at each line in an interview. |
| `triage/guardrails.py` | Pure function: `(classification, draft, retrieved) -> (status, reasons)` | Business rules must be deterministic and unit-testable, so they are **not** in a prompt. |
| Alembic | Schema migrations | Reproducible schema, including `CREATE EXTENSION vector` and the HNSW index. |
| PostgreSQL + pgvector | Relational data **and** vectors in one DB | No separate vector DB to run; can JOIN chunks to articles; transactions cover both. |

### Module dependency rule

```mermaid
flowchart TD
    routers["*/router.py"] --> services["tickets.service / kb.service"]
    services --> triage["triage.workflow"]
    triage --> kb["kb.service.search"]
    triage --> llm["llm.providers"]
    kb --> llm
    services --> core["core (config, db)"]
    triage --> core
```

Arrows point one way. `llm/` imports nothing from features; `triage/` never imports from `tickets/`. If you ever need the reverse arrow, that is a design smell.

---

## 3. Key design decisions (interview talking points)

1. **Explicit pipeline, not an agent.** The steps are always the same and always in the same order. An agent deciding "should I search the KB?" adds non-determinism and cost for zero benefit.
2. **Structured output everywhere the LLM speaks.** `with_structured_output(Model, method="json_schema")` returns a validated Pydantic object. No regex parsing of free text.
3. **LLM proposes, code decides.** The LLM suggests priority/confidence; Python rules decide `auto_ready` vs `needs_review`. Makes behaviour predictable and testable.
4. **Fail safe.** Any LLM error → ticket is still saved and routed to a human (`needs_review`), and the error is recorded.
5. **Synchronous triage.** `POST /tickets` waits for the result (a few seconds). Simpler than a job queue; fine for a demo/internal tool. FastAPI's `BackgroundTasks` is the next step if needed.
6. **Sync SQLAlchemy + `def` endpoints.** FastAPI runs plain `def` endpoints in a threadpool, so blocking DB/LLM calls don't freeze the event loop. Avoids learning async SQLAlchemy at the same time as everything else.
7. **Same embedding dimension for both providers (768).** One table, one index. The `embedding_model` column prevents mixing vectors from different models.

---

## 4. Request / data flow

### 4.1 Create ticket (main flow)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as tickets.router
    participant S as tickets.service
    participant W as triage.workflow
    participant K as kb.service
    participant L as Chat model (Gemini/Ollama)
    participant DB as PostgreSQL

    C->>R: POST /tickets {email, subject, body}
    R->>S: create_ticket(data)
    S->>DB: INSERT ticket (status=pending)
    S->>W: run_triage(ticket)
    W->>L: classify (structured output → Classification)
    W->>K: search(subject+body, k=4)
    K->>DB: SELECT ... ORDER BY embedding <=> :q LIMIT 4
    K-->>W: chunks + distances
    alt relevant chunks found
        W->>L: draft reply with passages (→ DraftReply)
    else none under threshold
        W-->>W: skip draft, reason = no_relevant_kb
    end
    W->>W: guardrails(classification, draft, chunks) → status, reasons
    W-->>S: TriageResult (+ step timings, or error)
    S->>DB: INSERT triage_run; UPDATE ticket (status, classification, draft)
    S-->>R: ticket
    R-->>C: 201 TicketOut
```

### 4.2 Add KB article

```
POST /kb/articles
  → INSERT kb_articles
  → RecursiveCharacterTextSplitter(chunk_size=800, overlap=100).split_text(content)
  → embeddings.embed_documents(chunks)          # one batched call
  → INSERT kb_chunks (article_id, chunk_index, text, embedding, embedding_model)
  → COMMIT (article + chunks in one transaction)
```

### 4.3 Ticket status lifecycle

```mermaid
stateDiagram-v2
    [*] --> pending: POST /tickets
    pending --> auto_ready: guardrails pass
    pending --> needs_review: guardrail triggered / LLM error / no KB match
    auto_ready --> approved: review approve|edit
    needs_review --> approved: review approve|edit
    auto_ready --> rejected: review reject
    needs_review --> rejected: review reject
    auto_ready --> pending: re-run triage
    needs_review --> pending: re-run triage
    approved --> [*]
    rejected --> [*]
```

`auto_ready` means "a human could send this with one click", **not** "sent".

---

## 5. LangChain + LLM workflow

### 5.1 Which LangChain pieces are used (and nothing more)

| LangChain piece | Package | Used for |
|-----------------|---------|----------|
| `ChatGoogleGenerativeAI` / `ChatOllama` | `langchain-google-genai` / `langchain-ollama` | Chat model per provider |
| `GoogleGenerativeAIEmbeddings` / `OllamaEmbeddings` | same | Embeddings per provider |
| `ChatPromptTemplate` | `langchain-core` | Prompt with variables |
| `.with_structured_output(PydanticModel, method="json_schema")` | `langchain-core` (model method) | Validated outputs |
| LCEL pipe: `prompt \| structured_model` | `langchain-core` | Compose prompt + model into one Runnable with `.invoke()` |
| `RecursiveCharacterTextSplitter` | `langchain-text-splitters` | Chunking KB articles |
| `DeterministicFakeEmbedding` | `langchain-core` | Tests without network |

Vector storage/search is done with **SQLAlchemy + `pgvector`** directly (one ORM, SQL you can read). `langchain-postgres`' `PGVectorStore` is a valid alternative (its older `PGVector` class is deprecated) but it manages its own tables, which would mean two ways to talk to the same DB.

### 5.2 Provider factory

```mermaid
flowchart LR
    ENV[".env<br/>LLM_PROVIDER, *_MODEL"] --> F["llm/providers.py"]
    F -->|gemini| G1["ChatGoogleGenerativeAI(model, temperature, timeout, max_retries)"]
    F -->|gemini| G2["GoogleGenerativeAIEmbeddings(model='gemini-embedding-001', output_dimensionality=768)"]
    F -->|ollama| O1["ChatOllama(model, base_url, temperature)"]
    F -->|ollama| O2["OllamaEmbeddings(model='nomic-embed-text', base_url)"]
```

Both return LangChain's common interfaces (`BaseChatModel`, `Embeddings`), so `workflow.py` just calls `.invoke()` / `.embed_query()` and never checks which provider it has. (LangChain's `init_chat_model("google_genai:...")` / `init_chat_model("ollama:...")` can do the same; an explicit `if/else` is used here because it's easier to read and to pass provider-specific args like `output_dimensionality` or `base_url`.)

### 5.3 The four steps

| Step | Type | Input | Output | Notes |
|------|------|-------|--------|-------|
| 1. Classify | LLM, structured | subject, body | `Classification` | temperature 0; enums enforced by `Literal[...]` types |
| 2. Retrieve | Embeddings + SQL | subject + body | list of `RetrievedChunk` | filter `distance <= RETRIEVAL_MAX_DISTANCE` and `embedding_model = current` |
| 3. Draft | LLM, structured | ticket, classification, numbered passages | `DraftReply` | "Use only the passages. If they don't answer it, say so and set low confidence." Skipped if step 2 is empty. |
| 4. Guardrails | Pure Python | outputs of 1–3 | `status`, `reasons[]` | Rules from requirements FR-12 |

LLM output contracts (`triage/llm_schemas.py`):

```python
class Classification(BaseModel):
    category: Literal["billing", "technical", "account", "shipping", "other"]
    priority: Literal["low", "medium", "high", "urgent"]
    sentiment: Literal["positive", "neutral", "negative"]
    summary: str = Field(max_length=200, description="One sentence summary of the issue")
    language: str = Field(description="ISO 639-1 code, e.g. 'en'")

class DraftReply(BaseModel):
    reply: str
    cited_article_ids: list[int] = Field(description="IDs of passages actually used")
    confidence: float = Field(ge=0.0, le=1.0)
    missing_info: str | None = None
```

The `description=` text is sent to the model as part of the JSON schema — it's effectively part of the prompt.

### 5.4 Why no agents / LangGraph / multi-agent

- The flow is **linear with one branch** (skip drafting if nothing relevant). An `if` statement expresses that perfectly.
- Agents choose tools in a loop → more LLM calls, less predictable, harder to test, harder to explain.
- Multi-agent would split one small job across "agents" that are really just two prompts.
- **When it *would* make sense:** if you add a step like "look up the customer's order status via an API only for shipping tickets" and want retries/branching/checkpoints, LangGraph's `StateGraph` is the natural upgrade. The four step functions map 1:1 to graph nodes, so this is an easy stretch goal.

---

## 6. Database design

```mermaid
erDiagram
    KB_ARTICLES ||--o{ KB_CHUNKS : "has"
    TICKETS ||--o{ TRIAGE_RUNS : "has"

    KB_ARTICLES {
        int id PK
        varchar title
        varchar category
        text content
        timestamptz created_at
    }
    KB_CHUNKS {
        int id PK
        int article_id FK "ON DELETE CASCADE"
        int chunk_index
        text text
        vector embedding "vector(768)"
        varchar embedding_model
        timestamptz created_at
    }
    TICKETS {
        int id PK
        varchar customer_email
        varchar subject
        text body
        varchar status "pending|auto_ready|needs_review|approved|rejected"
        varchar category "nullable"
        varchar priority "nullable"
        varchar sentiment "nullable"
        text summary "nullable"
        text draft_reply "nullable"
        jsonb cited_article_ids
        float confidence "nullable"
        jsonb review_reasons
        text final_reply "nullable"
        text review_note "nullable"
        timestamptz reviewed_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    TRIAGE_RUNS {
        int id PK
        int ticket_id FK
        varchar status "succeeded|failed"
        varchar provider
        varchar chat_model
        varchar embedding_model
        varchar prompt_version
        jsonb classification
        jsonb retrieved "chunk ids + distances"
        jsonb draft
        jsonb step_timings "ms per step"
        int latency_ms
        text error "nullable"
        timestamptz created_at
    }
```

**Why this shape**

- `tickets` holds the **current** state (fast to list/filter); `triage_runs` holds the **history** (audit, provider comparison). Latest result is copied onto the ticket so the review queue doesn't need a join.
- `kb_chunks.embedding_model` lets search filter to comparable vectors and makes reindexing safe.
- Indexes:
  - `kb_chunks`: HNSW on `embedding` using `vector_cosine_ops`; b-tree on `article_id`.
  - `tickets`: b-tree on `(status, created_at DESC)` for the review queue; on `category`.
  - `triage_runs`: b-tree on `ticket_id`.
- Status/category/priority are `VARCHAR` + `CHECK` constraints (easy to change in a migration; native PG enums are awkward to alter).

**The vector search query** (what `kb.service.search` does, in SQL terms):

```sql
SELECT c.id, c.article_id, a.title, c.text,
       c.embedding <=> :query_vec AS distance      -- cosine distance (0 = identical)
FROM kb_chunks c JOIN kb_articles a ON a.id = c.article_id
WHERE c.embedding_model = :model
ORDER BY c.embedding <=> :query_vec
LIMIT :k;
```

---

## 7. Configuration

`.env` (see `.env.example`):

```
DATABASE_URL=postgresql+psycopg://triage:triage@localhost:5432/triagedesk
LLM_PROVIDER=gemini                 # gemini | ollama
GOOGLE_API_KEY=...                  # only needed for gemini
GEMINI_CHAT_MODEL=gemini-3.7-flash
GEMINI_EMBED_MODEL=gemini-embedding-001
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
EMBEDDING_DIM=768
LLM_TIMEOUT_SECONDS=60
RETRIEVAL_K=4
RETRIEVAL_MAX_DISTANCE=0.5
CONFIDENCE_THRESHOLD=0.7
```

---

## 8. Folder structure

```
triagedesk/
├── app/
│   ├── main.py                  # create FastAPI app, include routers, exception handlers
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings), get_settings()
│   │   ├── db.py                # engine, SessionLocal, Base, get_db()
│   │   └── logging.py           # basic structured logging setup
│   ├── llm/
│   │   └── providers.py         # get_chat_model(), get_embeddings(), active_model_info()
│   ├── kb/
│   │   ├── models.py            # KbArticle, KbChunk (SQLAlchemy)
│   │   ├── schemas.py           # ArticleIn/Out, SearchIn, SearchHit (Pydantic)
│   │   ├── service.py           # create_article, delete_article, search, reindex
│   │   └── router.py
│   ├── tickets/
│   │   ├── models.py            # Ticket, TriageRun
│   │   ├── schemas.py           # TicketIn/Out, ReviewIn, RunOut
│   │   ├── service.py           # create_ticket, retriage, review, list, stats
│   │   └── router.py            # /tickets, /stats
│   ├── triage/
│   │   ├── llm_schemas.py       # Classification, DraftReply
│   │   ├── prompts.py           # CLASSIFY_PROMPT, DRAFT_PROMPT, PROMPT_VERSION
│   │   ├── guardrails.py        # evaluate(...) -> (status, reasons)
│   │   └── workflow.py          # TriageWorkflow.run(ticket) -> TriageResult
│   └── health/router.py
├── alembic/                     # env.py + versions/
├── alembic.ini
├── data/
│   ├── kb_articles/*.md         # ~10 sample help articles
│   └── eval_tickets.jsonl       # ~20 labelled tickets for eval
├── scripts/
│   ├── seed_kb.py
│   └── eval_triage.py
├── tests/
│   ├── conftest.py              # fake LLM, fake embeddings, test DB session
│   ├── unit/test_guardrails.py
│   ├── unit/test_workflow.py
│   ├── unit/test_chunking.py
│   └── integration/test_api.py
├── .env.example
├── docker-compose.yml           # db (pgvector) + api
├── Dockerfile
├── pyproject.toml
└── README.md
```

Each feature folder has the same four files (`models`, `schemas`, `service`, `router`), so once you understand one you understand all of them.

---

## 9. What we'd add later (and the trigger for adding it)

| Addition | Add it when… |
|----------|--------------|
| `BackgroundTasks` or a job table | Triage latency makes `POST /tickets` feel slow for clients |
| LangGraph `StateGraph` | A step needs conditional tool calls, loops, or retries per node |
| Auth (API key / OAuth2) | More than one user or anything public |
| Hybrid search (full-text + vector) | Tickets use exact product codes/SKUs that embeddings miss |
| Redis / queue | Multiple app instances or very high volume — not before |
