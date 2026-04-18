from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from langfuse import Langfuse
from functools import lru_cache
import httpx
import os
import time

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")
LLM_MODEL_MULTILINGUAL = os.getenv("LLM_MODEL_MULTILINGUAL", "mistral")
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "4"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
COLLECTION_NAME = "mortgage_docs"

# Basic ASCII range check — questions outside ASCII are non-English
def _is_english(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False

_lf_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
langfuse = Langfuse(
    public_key=_lf_key,
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
    host=os.getenv("LANGFUSE_HOST", "http://langfuse:3000"),
    enabled=bool(_lf_key),
)

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
        limit=state.get("top_k", 3),
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
        if r.score > 0.15  # POC threshold — short docs score lower than multi-chunk corpora
    ]
    return {**state, "chunks": chunks}


def build_context(state: RAGState) -> RAGState:
    if not state["chunks"]:
        return {**state, "context": "", "sources": []}

    # 200 words per chunk keeps total prompt under ~700 tokens for faster CPU inference
    def truncate(text: str, max_words: int = 200) -> str:
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
    # Route to multilingual model when question contains non-ASCII characters
    model = LLM_MODEL if _is_english(state["question"]) else LLM_MODEL_MULTILINGUAL
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a mortgage underwriting assistant. "
                        "Answer using ONLY the provided context. "
                        "Be concise (2-3 sentences). Cite numbers (DTI, credit score, LTV) when available. "
                        "IMPORTANT: Reply in the same language the user used in their question."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"CONTEXT:\n{state['context']}\n\n"
                        f"QUESTION: {state['question']}\n\n"
                        + (
                            "IMPORTANT: Your answer MUST be written in Hindi only."
                            if not _is_english(state["question"])
                            else ""
                        )
                    ),
                },
            ],
            "options": {
                "num_thread": OLLAMA_NUM_THREAD,
                "num_predict": 200,
                "temperature": 0.1,
                "top_k": 10,
                "top_p": 0.9,
            },
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    answer = response.json()["message"]["content"].strip()
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

    # ── Retrieval span ──
    t_retrieve = time.perf_counter()
    span_retrieve = trace.span(name="retrieve", input={"question": question, "loan_id": loan_id})

    try:
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
    except httpx.TimeoutException as e:
        # Ollama timed out — record in trace before re-raising
        elapsed_ms = int((time.perf_counter() - t_retrieve) * 1000)
        span_retrieve.end(
            output={"error": "timeout", "latency_ms": elapsed_ms},
            level="ERROR",
        )
        trace.update(
            output={"error": f"LLM timeout after {elapsed_ms}ms"},
            metadata={"timed_out": True, "elapsed_ms": elapsed_ms, "timeout_setting": OLLAMA_TIMEOUT},
            level="ERROR",
        )
        langfuse.flush()
        raise
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t_retrieve) * 1000)
        span_retrieve.end(output={"error": str(e), "latency_ms": elapsed_ms}, level="ERROR")
        trace.update(
            output={"error": str(e)},
            metadata={"failed": True, "elapsed_ms": elapsed_ms},
            level="ERROR",
        )
        langfuse.flush()
        raise

    retrieval_ms = int((time.perf_counter() - t_retrieve) * 1000)
    span_retrieve.end(output={"chunk_count": len(result["chunks"]), "latency_ms": retrieval_ms})

    # ── Generate span — timed separately from retrieval ──
    t_gen = time.perf_counter()
    span_gen = trace.span(name="generate", input={"context_chars": len(result["context"]), "chunk_count": len(result["chunks"])})
    gen_ms = int((time.perf_counter() - t_gen) * 1000)
    span_gen.end(output={"answer_chars": len(result["answer"]), "latency_ms": gen_ms})

    trace.update(
        output={"answer": result["answer"], "sources": result["sources"]},
        metadata={
            "chunk_count": len(result["chunks"]),
            "retrieval_ms": retrieval_ms,
            "total_ms": int((time.perf_counter() - t_retrieve) * 1000),
        },
    )
    langfuse.flush()

    return result
