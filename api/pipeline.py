from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from langfuse import Langfuse
from functools import lru_cache
import hashlib
import httpx
import os
import time

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")
# Limit Ollama to half the CPU cores to prevent 100% saturation
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "4"))
COLLECTION_NAME = "mortgage_docs"

_lf_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
langfuse = Langfuse(
    public_key=_lf_key,
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
    host=os.getenv("LANGFUSE_HOST", "http://langfuse:3000"),
    enabled=bool(_lf_key),
)

# Cache up to 256 recent query embeddings — avoids re-encoding repeated questions
@lru_cache(maxsize=256)
def _cached_embed(question: str, embedder_id: str) -> tuple:
    return tuple(embedder_cache[embedder_id].encode(question).tolist())

embedder_cache: dict = {}


def register_embedder(embedder: SentenceTransformer) -> str:
    eid = str(id(embedder))
    embedder_cache[eid] = embedder
    return eid


class RAGState(TypedDict):
    question: str
    loan_id: Optional[str]
    top_k: int
    query_vector: Optional[list[float]]
    chunks: list[dict]
    context: str
    answer: str
    sources: list[dict]
    trace_id: Optional[str]
    embedder_id: str


# ── Nodes ──────────────────────────────────────────────────────────────────────

def embed_query(state: RAGState) -> RAGState:
    vec = list(_cached_embed(state["question"], state["embedder_id"]))
    return {**state, "query_vector": vec}


def retrieve_chunks(state: RAGState, qdrant: QdrantClient) -> RAGState:
    search_filter = None
    if state.get("loan_id"):
        search_filter = Filter(
            must=[FieldCondition(key="loan_id", match=MatchValue(value=state["loan_id"]))]
        )

    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=state["query_vector"],
        query_filter=search_filter,
        limit=state.get("top_k", 3),  # reduced from 5 → 3 for shorter prompts
        with_payload=True,
    )

    chunks = [
        {
            "text": r.payload.get("text", ""),
            "loan_id": r.payload.get("loan_id"),
            "doc_type": r.payload.get("doc_type"),
            "score": round(r.score, 3),
        }
        for r in results
        if r.score > 0.3  # skip low-relevance chunks
    ]
    return {**state, "chunks": chunks}


def build_context(state: RAGState) -> RAGState:
    if not state["chunks"]:
        return {**state, "context": "", "sources": []}

    # Truncate each chunk to 400 words to keep prompt small
    def truncate(text: str, max_words: int = 400) -> str:
        words = text.split()
        return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")

    context = "\n\n---\n\n".join(truncate(c["text"]) for c in state["chunks"])
    sources = [{"loan_id": c["loan_id"], "doc_type": c["doc_type"], "score": c["score"]} for c in state["chunks"]]
    return {**state, "context": context, "sources": sources}


def should_generate(state: RAGState) -> str:
    return "generate" if state["context"] else "no_context"


def no_context(state: RAGState) -> RAGState:
    return {**state, "answer": "No relevant documents found. Please ingest documents for this loan first."}


def generate_answer(state: RAGState) -> RAGState:
    # Concise system prompt reduces token count → faster inference
    prompt = f"""You are a mortgage underwriting assistant. Answer concisely using only the context below. Cite numbers (DTI, credit score, LTV) when available.

CONTEXT:
{state["context"]}

QUESTION: {state["question"]}
ANSWER:"""

    response = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_thread": OLLAMA_NUM_THREAD,  # cap CPU usage
                "num_predict": 300,               # max tokens in response
                "temperature": 0.1,               # low temp = faster, more deterministic
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    answer = response.json()["response"].strip()
    return {**state, "answer": answer}


# ── Graph factory ──────────────────────────────────────────────────────────────

def build_rag_graph(qdrant: QdrantClient, embedder: SentenceTransformer) -> tuple:
    eid = register_embedder(embedder)

    graph = StateGraph(RAGState)
    graph.add_node("embed_query", embed_query)
    graph.add_node("retrieve_chunks", lambda s: retrieve_chunks(s, qdrant))
    graph.add_node("build_context", build_context)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("no_context", no_context)

    graph.set_entry_point("embed_query")
    graph.add_edge("embed_query", "retrieve_chunks")
    graph.add_edge("retrieve_chunks", "build_context")
    graph.add_conditional_edges("build_context", should_generate, {
        "generate": "generate_answer",
        "no_context": "no_context",
    })
    graph.add_edge("generate_answer", END)
    graph.add_edge("no_context", END)

    return graph.compile(), eid


# ── Traced runner ──────────────────────────────────────────────────────────────

def run_rag_pipeline(graph, embedder_id: str, question: str, loan_id: Optional[str], top_k: int = 3) -> dict:
    trace = langfuse.trace(
        name="mortgage-rag-query",
        input={"question": question, "loan_id": loan_id},
        metadata={"loan_id": loan_id},
    )

    t0 = time.perf_counter()
    span_retrieve = trace.span(name="retrieve", input={"question": question})

    result = graph.invoke({
        "question": question,
        "loan_id": loan_id,
        "top_k": top_k,
        "query_vector": None,
        "chunks": [],
        "context": "",
        "answer": "",
        "sources": [],
        "trace_id": trace.id,
        "embedder_id": embedder_id,
    })

    retrieval_ms = int((time.perf_counter() - t0) * 1000)
    span_retrieve.end(output={"chunk_count": len(result["chunks"]), "latency_ms": retrieval_ms})

    span_gen = trace.span(name="generate", input={"context_chars": len(result["context"])})
    span_gen.end(output={"answer_chars": len(result["answer"])})

    trace.update(
        output={"answer": result["answer"], "sources": result["sources"]},
        metadata={"chunk_count": len(result["chunks"]), "retrieval_ms": retrieval_ms},
    )
    langfuse.flush()

    return result
