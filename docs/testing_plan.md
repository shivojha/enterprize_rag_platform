# Testing Plan — Mortgage RAG Platform POC

> **Scope:** Developer machine only. Manual and scripted tests against local Docker Compose stack.

---

## Prerequisites

```bash
# 1. Start all services
docker compose up -d

# 2. Pull Mistral model (first time only, ~4 GB)
bash setup.sh

# 3. Load demo data
bash load_demo_data.sh

# 4. Verify all services healthy
docker compose ps
```

Expected: all 9 containers show `healthy` or `running`.

---

## 1. Infrastructure Health Checks

| Test | Command | Expected |
|---|---|---|
| API alive | `curl http://localhost:8002/health` | `{"status":"ok","collection":"mortgage_docs"}` |
| Qdrant alive | `curl http://localhost:6334/collections` | JSON with `mortgage_docs` collection |
| Ollama alive | `curl http://localhost:11435/api/tags` | JSON listing `mistral` model |
| LangFuse alive | `curl http://localhost:3002` | HTML (302 redirect to login) |
| Redis alive | `docker compose exec redis redis-cli ping` | `PONG` |
| Postgres alive | `docker compose exec postgres pg_isready -U raguser` | `accepting connections` |

---

## 2. Ingestion Pipeline Tests

### 2a. Single Document Ingest

```bash
curl -s -X POST "http://localhost:8002/ingest/LN-2024-001?doc_type=application" \
  -F "file=@data/sample_loans/LN-2024-001/application.txt" | python3 -m json.tool
```

**Expected response:**
```json
{
  "job_id": "<uuid>",
  "loan_id": "LN-2024-001",
  "doc_type": "application",
  "message": "Queued for ingestion"
}
```

### 2b. Status Polling (wait ~5–15 seconds)

```bash
curl -s "http://localhost:8002/loans/LN-2024-001/status" | python3 -m json.tool
```

**Expected:** `"status": "completed"` with `chunk_count > 0`

### 2c. Verify Vectors in Qdrant

```bash
curl -s "http://localhost:6334/collections/mortgage_docs" | python3 -m json.tool
```

**Expected:** `vectors_count > 0`

### 2d. Unsupported Loan (no docs ingested)

Query loan with no documents:
```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the credit score?", "loan_id": "LN-NONE-999"}'
```

**Expected:** HTTP 404 `"No relevant documents found."`

---

## 3. Query Pipeline Tests

Run all five with the full demo data loaded (`bash load_demo_data.sh`).

### 3a. Basic Factual Query

```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the loan amount?", "loan_id": "LN-2024-001"}' \
  | python3 -m json.tool
```

**Expected:** `answer` contains a dollar figure; `sources` has at least 1 entry with `score > 0.3`

### 3b. Cross-Document Query

```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the DTI ratio and credit score?", "loan_id": "LN-2024-003"}' \
  | python3 -m json.tool
```

**Expected:** Answer cites both DTI and credit score numbers from ingested credit report.

### 3c. Policy Query

```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the minimum credit score for FHA?", "loan_id": "policy"}' \
  | python3 -m json.tool
```

**Expected:** Answer references FHA guidelines (580+ credit score).

### 3d. Out-of-Context Query

```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the weather today?", "loan_id": "LN-2024-001"}' \
  | python3 -m json.tool
```

**Expected:** Answer reflects uncertainty or deflects — model should not hallucinate mortgage data.

### 3e. Cross-Loan Isolation

Query LN-2024-001 asking about LN-2024-003's credit score:
```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Robert Johnson credit score?", "loan_id": "LN-2024-001"}' \
  | python3 -m json.tool
```

**Expected:** Answer should not leak data from LN-2024-003. Sources should only reference LN-2024-001 documents.

### 3f. Top-K Override

```bash
curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the loan", "loan_id": "LN-2024-005", "top_k": 1}' \
  | python3 -m json.tool
```

**Expected:** `sources` has exactly 1 entry (or 0 if below score threshold).

---

## 4. Embedding Cache Test

Send the same question twice and verify the second call is faster:

```bash
time curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the loan amount?", "loan_id": "LN-2024-001"}' > /dev/null

time curl -s -X POST "http://localhost:8002/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the loan amount?", "loan_id": "LN-2024-001"}' > /dev/null
```

**Expected:** Second call slightly faster (embedding step skipped via `lru_cache`).

---

## 5. Observability Tests

### 5a. LangFuse Traces

1. Open [http://localhost:3002](http://localhost:3002)
2. Login: `admin@mortgage.local` / `mortgage123`
3. Navigate to **Traces**
4. Run a query (section 3a above)
5. Refresh — new trace should appear named `mortgage-rag-query`

**Expected:** Trace shows two spans — `retrieve` and `generate` — with latency in milliseconds.

### 5b. Token / Char Count

In LangFuse trace detail:
- `retrieve` span → `output.chunk_count` should be 1–3
- `generate` span → `output.answer_chars` should be > 0

---

## 6. UI Smoke Test

1. Open [http://localhost:5174](http://localhost:5174)
2. Verify 5 loan cards appear in sidebar
3. Click **LN-2024-003 (Underwriting)** — metrics panel should show credit score, DTI, loan amount
4. Type "What documents have been submitted?" in the chat box and press Enter
5. Verify an answer appears in the chat panel within 120 seconds
6. Click **Documents** tab — verify ingested files are listed with status `completed`

---

## 7. Bulk Test (Scripted)

```bash
bash test_pipeline.sh
```

Runs all 5 loan queries sequentially and prints pass/fail for each.

---

## 8. Known Limitations (POC)

| Limitation | Impact |
|---|---|
| CPU inference only | Queries take 30–120 seconds depending on hardware |
| No auth — any curl can query any loan | Acceptable locally; not for production |
| LRU cache is in-process | Cache cold on container restart |
| Celery worker takes 5–30s per document | Status stays `processing` briefly |
| LangFuse may show stale trace lag | Spans flushed async; allow 5–10s |
