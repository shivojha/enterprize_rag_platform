# Requirements — Mortgage RAG Platform POC

> **Scope:** Developer machine only (Docker Compose, local laptop). Not for production use.

---

## In Scope

### Functional Requirements

| # | Requirement | Endpoint / Component |
|---|---|---|
| F1 | Ingest PDF or TXT mortgage documents per loan ID | `POST /ingest/{loan_id}` |
| F2 | Chunk documents into 500-token segments (50-token overlap) | Celery worker |
| F3 | Embed chunks using `all-MiniLM-L6-v2` (384-dim vectors) | Celery worker |
| F4 | Store vectors in Qdrant with loan-level payload filter | Qdrant collection `mortgage_docs` |
| F5 | Accept natural language questions about a specific loan | `POST /query` |
| F6 | Retrieve top-3 semantically relevant chunks (cosine, score > 0.3) | LangGraph `retrieve_chunks` node |
| F7 | Generate a concise answer using local Mistral 7B via Ollama | LangGraph `generate_answer` node |
| F8 | Return answer with source attribution (doc_type, score) | `QueryResponse.sources` |
| F9 | Track loan document ingestion status (queued → processing → completed) | `GET /loans/{loan_id}/status` |
| F10 | Display 5 demo loans across all pipeline stages in a browser UI | React + Vite UI |
| F11 | Trace every query with LangFuse (spans: retrieve, generate) | `pipeline.py run_rag_pipeline` |
| F12 | Cache repeated query embeddings in-process (LRU, 256 entries) | `@lru_cache` in pipeline.py |

### Non-Functional Requirements (POC-level)

| # | Requirement | Target |
|---|---|---|
| NF1 | All services run on a single developer laptop | Docker Compose |
| NF2 | Zero cloud cost — no external APIs or paid services | Local models only |
| NF3 | Query response time (end-to-end) | < 120 seconds on CPU |
| NF4 | Document ingestion (async, background) | Celery + Redis queue |
| NF5 | Embedding model loaded once at worker startup | Shared model cache |
| NF6 | Support PDF and plain-text documents | pypdf + text fallback |

### Demo Data

Five loan scenarios covering all pipeline stages:
- **LN-2024-001** — Application Submitted (John Smith)
- **LN-2024-002** — Document Review (Maria Garcia)
- **LN-2024-003** — Underwriting (Robert Johnson)
- **LN-2024-004** — Approved (Sarah Chen)
- **LN-2024-005** — Closing (Michael Brown)
- **policy** — FHA Policy Guidelines (cross-loan reference)

---

## Out of Scope

### Security (not implemented in this POC)

| # | Item | Reason Excluded |
|---|---|---|
| OS1 | API authentication (JWT, OAuth2, API keys) | POC only; no external users |
| OS2 | Role-based access control (RBAC) | Single developer context |
| OS3 | Secrets management (Vault, AWS SSM) | Credentials in `.env` acceptable locally |
| OS4 | TLS/mTLS between internal Docker services | Localhost Docker network |
| OS5 | Rate limiting | No public exposure |
| OS6 | Input sanitization beyond Pydantic types | Demo inputs only |
| OS7 | File upload size / MIME type enforcement | Trusted demo files only |
| OS8 | Audit logging (GLBA / GDPR compliance) | No real PII |

### Infrastructure

| # | Item | Reason Excluded |
|---|---|---|
| OI1 | Kubernetes / Helm deployment | Developer machine only |
| OI2 | CI/CD pipeline | No code repository integration |
| OI3 | Database connection pooling | Single-user local load |
| OI4 | Horizontal scaling (multi-worker, multi-API) | Single Docker Compose stack |
| OI5 | Prometheus metrics + alerting | LangFuse is sufficient for POC |
| OI6 | Database migrations (Alembic) | Schema seeded once via init.sql |
| OI7 | Container image vulnerability scanning | Not published to a registry |

### Features

| # | Item | Reason Excluded |
|---|---|---|
| OF1 | Multi-tenant isolation | Single org demo |
| OF2 | Document deletion / re-ingestion API | Not needed for demo |
| OF3 | Streaming LLM responses | CPU inference too slow to benefit |
| OF4 | User authentication in UI | POC UI, no login flow |
| OF5 | PII masking in API responses | Synthetic demo data only |
| OF6 | Cross-loan queries (all loans at once) | Loan-scoped filter intentional |
| OF7 | GPU acceleration | Laptop CPU only |
| OF8 | ClickHouse / S3 for LangFuse v3 | Resource-heavy; v2 used instead |

---

## Constraints

- **Platform:** macOS or Linux laptop with Docker Desktop
- **RAM:** Minimum 16 GB recommended (Ollama ~6 GB, all services ~10 GB total)
- **Disk:** ~8 GB for Docker images + Mistral model (~4 GB)
- **CPU:** 4+ cores; Ollama capped at 4 threads (`OLLAMA_NUM_THREAD=4`)
- **Network:** No internet required after initial `docker compose pull` + `ollama pull mistral`
