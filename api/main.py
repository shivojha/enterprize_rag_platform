from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from sentence_transformers import SentenceTransformer
from celery import Celery
from pipeline import build_rag_graph, run_rag_pipeline
import psycopg2
import json
import os
import uuid
import shutil
from typing import Optional

app = FastAPI(title="Mortgage RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
POSTGRES_URL = os.getenv("POSTGRES_URL")
assert POSTGRES_URL, "POSTGRES_URL environment variable is required"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME = "mortgage_docs"
DATA_DIR = "/app/data"

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embedder = SentenceTransformer(EMBEDDING_MODEL)
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
rag_graph = None
rag_embedder_id = None


def get_db():
    return psycopg2.connect(POSTGRES_URL)


def ensure_collection():
    collections = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME not in collections:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


@app.on_event("startup")
async def startup():
    global rag_graph, rag_embedder_id
    ensure_collection()
    rag_graph, rag_embedder_id = build_rag_graph(qdrant, embedder)


# ── Ingestion ──────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    job_id: str
    loan_id: str
    doc_type: str
    message: str


@app.post("/ingest/{loan_id}", response_model=IngestResponse)
async def ingest_document(
    loan_id: str,
    doc_type: str,
    file: UploadFile = File(...),
):
    os.makedirs(f"{DATA_DIR}/{loan_id}", exist_ok=True)
    file_path = f"{DATA_DIR}/{loan_id}/{doc_type}_{file.filename}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO documents (loan_id, doc_type, file_path, status) VALUES (%s, %s, %s, 'queued') "
        "ON CONFLICT DO NOTHING",
        (loan_id, doc_type, file_path),
    )
    db.commit()
    cur.close()
    db.close()

    job_id = str(uuid.uuid4())
    celery_app.send_task("ingest_document", kwargs={
        "job_id": job_id, "loan_id": loan_id,
        "doc_type": doc_type, "file_path": file_path,
    })

    return IngestResponse(job_id=job_id, loan_id=loan_id, doc_type=doc_type, message="Queued for ingestion")


# ── Query (LangGraph orchestrated) ────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    loan_id: Optional[str] = None
    top_k: int = 5


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]
    loan_id: Optional[str]
    trace_id: Optional[str] = None


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    try:
        result = run_rag_pipeline(
            graph=rag_graph,
            embedder_id=rag_embedder_id,
            question=req.question,
            loan_id=req.loan_id,
            top_k=req.top_k,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if not result["answer"]:
        raise HTTPException(status_code=404, detail="No relevant documents found.")

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO query_log (loan_id, question, answer, sources) VALUES (%s, %s, %s, %s)",
        (req.loan_id, req.question, result["answer"], json.dumps(result["sources"])),
    )
    db.commit()
    cur.close()
    db.close()

    return QueryResponse(
        answer=result["answer"],
        sources=result["sources"],
        loan_id=req.loan_id,
        trace_id=result.get("trace_id"),
    )


# ── Status ─────────────────────────────────────────────────────────────────────

@app.get("/loans/{loan_id}/status")
async def loan_status(loan_id: str):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT doc_type, status, chunk_count, ingested_at FROM documents WHERE loan_id = %s", (loan_id,))
    rows = cur.fetchall()
    cur.close()
    db.close()
    return {"loan_id": loan_id, "documents": [
        {"doc_type": r[0], "status": r[1], "chunks": r[2], "ingested_at": str(r[3])}
        for r in rows
    ]}


@app.get("/health")
async def health():
    return {"status": "ok", "collection": COLLECTION_NAME}
