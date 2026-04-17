import os
import json
import uuid
import redis
import psycopg2
from celery import Celery
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POSTGRES_URL = os.getenv("POSTGRES_URL")
assert POSTGRES_URL, "POSTGRES_URL environment variable is required"
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
COLLECTION_NAME = "mortgage_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
embedder = SentenceTransformer(EMBEDDING_MODEL)
r = redis.from_url(REDIS_URL)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
        i += size - overlap
    return chunks


def extract_text(file_path: str) -> str:
    if file_path.endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif file_path.endswith(".txt"):
        with open(file_path, "r") as f:
            return f.read()
    else:
        with open(file_path, "r", errors="ignore") as f:
            return f.read()


@app.task(name="ingest_document")
def ingest_document(job_id: str, loan_id: str, doc_type: str, file_path: str):
    db = psycopg2.connect(POSTGRES_URL)
    cur = db.cursor()

    try:
        cur.execute("UPDATE documents SET status = 'processing' WHERE loan_id = %s AND doc_type = %s", (loan_id, doc_type))
        db.commit()

        text = extract_text(file_path)
        if not text.strip():
            raise ValueError(f"No text extracted from {file_path}")

        chunks = chunk_text(text)
        embeddings = embedder.encode(chunks, batch_size=32, show_progress_bar=False)

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist(),
                    payload={
                        "loan_id": loan_id,
                        "doc_type": doc_type,
                        "chunk_index": i,
                        "text": chunk,
                        "file_path": file_path,
                    },
                )
            )

        # Upsert in batches of 100
        for batch_start in range(0, len(points), 100):
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points[batch_start : batch_start + 100])

        cur.execute(
            "UPDATE documents SET status = 'completed', chunk_count = %s, ingested_at = NOW() WHERE loan_id = %s AND doc_type = %s",
            (len(chunks), loan_id, doc_type),
        )
        db.commit()
        print(f"[OK] {loan_id}/{doc_type} — {len(chunks)} chunks ingested")

    except Exception as e:
        cur.execute("UPDATE documents SET status = 'failed' WHERE loan_id = %s AND doc_type = %s", (loan_id, doc_type))
        db.commit()
        print(f"[ERROR] {loan_id}/{doc_type}: {e}")
        raise

    finally:
        cur.close()
        db.close()


# Poll Redis queue (alternative to Celery beat for simplicity)
def run_queue_poller():
    print("Worker polling Redis queue...")
    while True:
        item = r.brpop("ingest_queue", timeout=5)
        if item:
            _, data = item
            payload = json.loads(data)
            ingest_document.delay(**payload)
