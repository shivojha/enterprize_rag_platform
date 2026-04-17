# Mortgage RAG Platform — Documentation

> **Developer Machine Only** — Zero-cost POC running entirely on Docker Compose.
> No cloud accounts or API keys required to run.

---

## What This POC Does

This platform demonstrates a **Retrieval Augmented Generation (RAG)** pipeline applied to mortgage loan processing. It answers natural language questions about a loan — *"What is the borrower's DTI ratio?"*, *"Does this application meet FHA guidelines?"* — by retrieving relevant content from ingested documents and generating a concise answer using a local LLM.

The end-to-end flow:

```text
Loan Officer uploads PDF/TXT document
        ↓
Celery worker chunks, embeds, and stores vectors in Qdrant
        ↓
User asks a question in the UI
        ↓
LangGraph orchestrates: embed question → vector search → build context → LLM generation
        ↓
Answer returned with source attribution and LangFuse trace
```

Five demo loans cover every stage of the mortgage pipeline — Application Submitted, Document Review, Underwriting, Approved, and Closing — with realistic synthetic documents (applications, appraisals, credit reports, closing disclosures, FHA policy guidelines).

---

## Enterprise RAG Skills Targeted

This POC is designed as a learning and demonstration platform for the following enterprise RAG competencies:

### 1. Document Ingestion Pipeline

- Async job queue (Celery + Redis) for background processing
- PDF and plain-text extraction with chunking (500 tokens, 50-token overlap)
- Batch vector upsert to a managed vector store

### 2. Semantic Search & Retrieval

- Dense vector embeddings (`all-MiniLM-L6-v2`, 384-dim) for meaning-based search
- Cosine similarity ANN search in Qdrant with loan-scoped payload filtering
- Relevance threshold filtering (score > 0.3) to suppress low-quality matches

### 3. LLM Orchestration with LangGraph

- Stateful multi-node graph: `embed_query → retrieve_chunks → build_context → generate_answer`
- Conditional branching (no-context fallback vs. generation path)
- In-process embedding cache (`lru_cache`) to avoid re-encoding repeated queries

### 4. Prompt Engineering for Domain Tasks

- Concise system prompt anchored to retrieved context only
- Instruction to cite numerical facts (DTI, credit score, LTV)
- Controlled output length (`num_predict=300`) and low temperature (0.1) for factual answers

### 5. Observability & Tracing

- Per-query LangFuse traces with named spans (`retrieve`, `generate`)
- Latency, chunk count, and answer length tracked per request
- Query log persisted to PostgreSQL for audit and replay

### 6. API Design & Async Patterns

- REST API (FastAPI) with typed request/response models
- Fire-and-forget ingestion (returns job ID immediately; worker processes async)
- Status polling endpoint for document ingestion lifecycle

### 7. Infrastructure as Code (Local)

- Full stack defined in a single `docker-compose.yml`
- Health checks and service dependency ordering for reliable startup
- Environment-variable-driven config; secrets externalized to `.env`

### 8. Deployment Readiness Progression

- POC: Docker Compose (this repo)
- Next: Free cloud tier (Railway, Neon, Qdrant Cloud, Groq, Vercel)
- Enterprise: Azure Container Apps, Azure OpenAI, AI Search, Key Vault

---

## Tech Stack

| Layer | Technology | Role |
| --- | --- | --- |
| **UI** | React 18 + Vite | Loan pipeline dashboard and chat interface |
| **API** | FastAPI + Uvicorn | REST endpoints: ingest, query, status |
| **Orchestration** | LangGraph 0.2 | Stateful RAG pipeline graph |
| **Embeddings** | sentence-transformers `all-MiniLM-L6-v2` | 384-dim semantic vectors |
| **Vector DB** | Qdrant | ANN search with cosine similarity and payload filters |
| **LLM** | Ollama + Mistral 7B | Local CPU inference, no API key needed |
| **Async Queue** | Celery 5.4 + Redis 7 | Background document ingestion jobs |
| **Metadata DB** | PostgreSQL 16 | Loan records, document status, query log |
| **Observability** | LangFuse v2 (self-hosted) | Traces, spans, latency per query |
| **PDF Parsing** | pypdf 4.3 | Text extraction from mortgage PDFs |
| **HTTP Client** | httpx | Async calls to Ollama API |
| **Containerisation** | Docker Compose | Single-command local stack |

---

## Quick Start

```bash
# Clone
git clone https://github.com/shivojha/enterprize_rag_platform
cd enterprize_rag_platform

# Configure (copy template, no changes needed for local run)
cp .env.example .env

# Start all services + pull Mistral model (~5 min first time, ~4 GB download)
bash setup.sh

# Ingest the 5 demo loans
bash load_demo_data.sh

# Open UI
open http://localhost:5174
```

---

## Service URLs

| Service | URL | Credentials |
| --- | --- | --- |
| React UI | <http://localhost:5174> | — |
| FastAPI docs (Swagger) | <http://localhost:8002/docs> | — |
| Qdrant dashboard | <http://localhost:6334/dashboard> | — |
| LangFuse observability | <http://localhost:3002> | `admin@mortgage.local` / `mortgage123` |

---

## Documentation Index

| Document | Description |
| --- | --- |
| [requirements.md](./requirements.md) | In-scope / out-of-scope requirements and constraints |
| [architecture.md](./architecture.md) | System architecture — Mermaid diagrams and tech stack |
| [testing_plan.md](./testing_plan.md) | Manual and scripted tests, expected outputs, known limits |
| [cloud_migration_free_tier.md](./cloud_migration_free_tier.md) | Next step: deploy to free cloud services (~$0/month) |
| [azure_migration.md](./azure_migration.md) | Enterprise Azure stack with managed services and security |

---

## Deployment Roadmap

```text
Developer Machine  →  Free Cloud Tier  →  Azure Enterprise
(Docker Compose)      (Railway, Neon,      (Container Apps,
  this repo           Qdrant Cloud,         Azure OpenAI,
                       Groq, Vercel)        AI Search, APIM)
```
