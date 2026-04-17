# Mortgage RAG Platform — Architecture

> **Developer Machine Only** — All services run locally via Docker Compose. No cloud infrastructure required.
> For cloud deployment see [Free Tier Migration](./cloud_migration_free_tier.md) → [Azure Stack](./azure_migration.md).

## System Overview

```mermaid
flowchart TD
    subgraph Client["Client"]
        UI["Browser UI (React + Vite :5174)"]
    end

    subgraph API["FastAPI :8002 (Python 3.11)"]
        IE["/ingest/{loan_id}"]
        QE["/query"]
        SE["/loans/{loan_id}/status"]
    end

    subgraph Orchestrator["LangGraph Orchestrator (langgraph 0.2)"]
        N1["embed_query (sentence-transformers)"]
        N2["retrieve_chunks (qdrant-client)"]
        N3["build_context"]
        N4{{"should_generate?"}}
        N5["generate_answer (httpx → Ollama)"]
        N6["no_context"]
        N1 --> N2 --> N3 --> N4
        N4 -->|"chunks found"| N5
        N4 -->|"empty"| N6
    end

    subgraph Queue["Async Layer"]
        RD["Redis :6380 (redis:7-alpine)"]
        WK["Celery Worker (celery 5.4)\nPDF Parser + Embedder"]
    end

    subgraph Storage["Storage"]
        QD["Qdrant :6334 (qdrant/qdrant)\nVector DB — cosine similarity"]
        PG["PostgreSQL :5433 (postgres:16-alpine)\nMetadata · Loans · Query Log"]
    end

    subgraph LLM["LLM Layer"]
        OL["Ollama :11435 (ollama/ollama)\nMistral 7B — CPU inference\nnum_thread=4, num_predict=300"]
    end

    subgraph Observability["Observability"]
        LF["LangFuse :3002 (langfuse/langfuse:2)\nTraces · Spans · Latency · Token counts"]
    end

    UI -->|"POST /ingest"| IE
    UI -->|"POST /query"| QE
    UI -->|"GET /status"| SE

    IE -->|"celery.send_task"| RD
    RD -->|"dequeue"| WK
    WK -->|"upsert vectors\n(all-MiniLM-L6-v2, 384-dim)"| QD
    WK -->|"UPDATE doc status"| PG

    QE --> Orchestrator
    N2 -->|"ANN search\ntop_k=3, score>0.3"| QD
    N5 -->|"POST /api/generate"| OL
    Orchestrator -->|"INSERT query_log"| PG
    Orchestrator -->|"trace + spans"| LF
```

## LangGraph Query Pipeline

```mermaid
stateDiagram-v2
    [*] --> embed_query
    note right of embed_query : all-MiniLM-L6-v2\nlru_cache(256) — skips re-encoding

    embed_query --> retrieve_chunks : 384-dim vector
    note right of retrieve_chunks : Qdrant ANN\ntop_k=3, score > 0.3

    retrieve_chunks --> build_context : scored chunks
    note right of build_context : truncate to 400 words/chunk

    build_context --> should_generate

    state should_generate <<choice>>
    should_generate --> generate_answer : chunks found
    should_generate --> no_context : empty results

    note right of generate_answer : Mistral 7B via Ollama\nnum_thread=4 · num_predict=300\ntemperature=0.1

    generate_answer --> [*] : answer + sources
    no_context --> [*] : fallback message
```

## Ingestion Pipeline

```mermaid
sequenceDiagram
    participant U as User
    participant A as FastAPI (Python)
    participant R as Redis (Celery broker)
    participant W as Celery Worker
    participant Q as Qdrant (vector store)
    participant P as PostgreSQL (metadata)

    U->>A: POST /ingest/LN-2024-001 (PDF/TXT)
    A->>P: INSERT documents (status=queued)
    A->>R: send_task(ingest_document)
    A-->>U: {job_id, status: queued}

    R->>W: dequeue job
    W->>P: UPDATE status=processing
    W->>W: extract text (pypdf / plain text)
    W->>W: chunk — 500 tokens, 50 overlap
    W->>W: embed — all-MiniLM-L6-v2 (384-dim)
    W->>Q: upsert PointStruct batch (100/req)
    W->>P: UPDATE status=completed, chunk_count=N
```

## Query Pipeline with Observability

```mermaid
sequenceDiagram
    participant U as User
    participant A as FastAPI
    participant G as LangGraph
    participant Q as Qdrant
    participant O as Ollama (Mistral 7B)
    participant P as PostgreSQL
    participant LF as LangFuse v2

    U->>A: POST /query {question, loan_id}
    A->>LF: trace.start (mortgage-rag-query)
    A->>G: graph.invoke(state)

    G->>G: embed_query — lru_cache hit or encode
    G->>LF: span(retrieve).start
    G->>Q: vector search (filter: loan_id, top_k=3)
    Q-->>G: chunks with scores
    G->>LF: span(retrieve).end (latency_ms)

    G->>G: build_context — truncate chunks
    G->>LF: span(generate).start
    G->>O: POST /api/generate\n{num_thread:4, num_predict:300, temp:0.1}
    O-->>G: answer
    G->>LF: span(generate).end

    G-->>A: {answer, sources}
    A->>P: INSERT query_log
    A->>LF: trace.update (output + metadata)
    A-->>U: {answer, sources, trace_id}
```

## Data Model

```mermaid
erDiagram
    LOANS {
        serial id PK
        varchar loan_id UK
        varchar borrower_name
        varchar loan_type
        decimal loan_amount
        text property_address
        varchar stage
        varchar status
        int credit_score
        decimal dti_ratio
        decimal interest_rate
        date submitted_date
        timestamp created_at
    }

    DOCUMENTS {
        serial id PK
        varchar loan_id FK
        varchar doc_type
        text file_path
        int chunk_count
        timestamp ingested_at
        varchar status
    }

    QUERY_LOG {
        serial id PK
        varchar loan_id
        text question
        text answer
        jsonb sources
        timestamp created_at
    }

    LOANS ||--o{ DOCUMENTS : "has"
    LOANS ||--o{ QUERY_LOG : "queried via"
```

## Docker Services

```mermaid
graph LR
    subgraph docker-compose ["docker-compose (local, $0)"]
        UI["ui\nReact + Vite\n:5174"]
        A["api\nFastAPI + LangGraph\n:8002"]
        W["worker\nCelery + sentence-transformers"]
        Q["qdrant\nVector DB\n:6334"]
        P["postgres\nMetadata\n:5433"]
        R["redis\nJob Queue\n:6380"]
        O["ollama\nMistral 7B\n:11435"]
        LF["langfuse\nObservability\n:3002"]
        LFP["langfuse-postgres\nLangFuse DB"]

        UI --> A
        A --> Q
        A --> P
        A --> R
        A --> O
        A --> LF
        W --> Q
        W --> P
        W --> R
        LF --> LFP
    end
```

## Tech Stack Summary

| Layer | Technology | Version |
| --- | --- | --- |
| UI | React + Vite | React 18 |
| API | FastAPI + Uvicorn | 0.115 |
| Orchestration | LangGraph | 0.2.55 |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | 3.1.1 |
| Vector DB | Qdrant | latest |
| LLM | Ollama + Mistral 7B | ollama:latest |
| Async Queue | Celery + Redis | 5.4 / redis:7 |
| Metadata DB | PostgreSQL | 16 |
| Observability | LangFuse v2 | langfuse:2 |
| PDF Parsing | pypdf | 4.3.1 |
| HTTP Client | httpx | 0.27.2 |
