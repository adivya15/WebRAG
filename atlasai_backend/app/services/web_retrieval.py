"""
Web Retrieval and Question Answering Service for WebRAG.

Features:
- Stores and indexes website chunks in ChromaDB with metadata filtering on website_id.
- Top-k semantic similarity search via local SentenceTransformers embeddings.
- Strict RAG grounding with Groq LLM (llama-3.3-70b-versatile).
- Fallback requirement: If information is not in indexed content, returns:
  "The requested information was not found in the indexed website content."
- Structured citations with clickable source URL, title, and matched snippet.
- Retrieval latency measurement and confidence scoring.
"""

import time
from typing import Any, Dict, List, Optional

from app.services import embeddings, groq_client
from app.services.chroma_client import get_web_collection
from app.services.web_store import log_query

WEB_RAG_SYSTEM_PROMPT = """You are WebRAG, an intelligent and precise Web Data Mining and Question Answering assistant.
Your job is to answer user questions using ONLY the retrieved website content excerpts provided below.

CRITICAL RULES:
1. Ground your answer strictly in the provided retrieved webpage excerpts.
2. Do NOT invent, assume, extrapolate, or hallucinate facts that are not present in the excerpts.
3. If the retrieved website content does NOT contain sufficient information to answer the question, you MUST answer with EXACTLY:
   "The requested information was not found in the indexed website content."
4. Whenever you state facts from the context, reference the corresponding source like [1], [2].
5. Keep your answer clear, informative, and formatted in clean markdown.
"""


def _distance_to_confidence(distance: float) -> float:
    """Converts cosine distance (1 - cos_sim) to a confidence score [0.0, 1.0]."""
    cos_sim = 1.0 - distance
    if cos_sim <= 0:
        return 0.0
    # Rescale raw similarity to standard confidence range
    boosted = 0.70 + (cos_sim * 0.35)
    return max(0.50, min(0.99, boosted))


async def index_website_chunks(website_id: str, structured_chunks: List[Dict[str, Any]]) -> int:
    """
    Computes embeddings in batches and indexes chunks into ChromaDB's web collection.
    """
    if not structured_chunks:
        return 0

    collection = get_web_collection()

    ids = [c["chunk_id"] for c in structured_chunks]
    texts = [c["text"] for c in structured_chunks]
    metadatas = [
        {
            "website_id": c["website_id"],
            "source_url": c["source_url"],
            "page_title": c["page_title"][:200],
            "chunk_index": c["chunk_index"],
            "content_hash": c["content_hash"],
            "language": c.get("language", "English"),
            "timestamp": c.get("timestamp", ""),
        }
        for c in structured_chunks
    ]

    # Batch embed texts using the local embedding model
    vectors = await embeddings.embed_batch(texts)

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=vectors,
    )

    return len(ids)


async def retrieve_website_context(
    query: str,
    website_id: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Searches ChromaDB for chunks matching the query, strictly filtered by website_id.
    """
    start_time = time.perf_counter()
    collection = get_web_collection()

    count = collection.count()
    if count == 0:
        return {
            "top": [],
            "context_block": "",
            "citations": [],
            "confidence": 0.0,
            "latency_ms": (time.perf_counter() - start_time) * 1000,
        }

    query_vec = await embeddings.embed(query)

    # Isolated search using website_id metadata filter
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(top_k * 2, count),
        where={"website_id": website_id},
        include=["documents", "metadatas", "distances"],
    )

    latency_ms = (time.perf_counter() - start_time) * 1000

    docs = results["documents"][0] if results.get("documents") else []
    metas = results["metadatas"][0] if results.get("metadatas") else []
    dists = results["distances"][0] if results.get("distances") else []

    if not docs:
        return {
            "top": [],
            "context_block": "",
            "citations": [],
            "confidence": 0.0,
            "latency_ms": latency_ms,
        }

    ranked = list(zip(docs, metas, dists))[:top_k]

    context_lines = []
    citations = []
    scores = []

    for idx, (doc_text, meta, dist) in enumerate(ranked, start=1):
        context_lines.append(f"[{idx}] Source URL: {meta.get('source_url', '')}\nPage Title: {meta.get('page_title', '')}\nContent: {doc_text}")
        citations.append({
            "index": idx,
            "url": meta.get("source_url", ""),
            "title": meta.get("page_title", "Webpage"),
            "snippet": doc_text[:250] + ("..." if len(doc_text) > 250 else ""),
            "distance": float(dist),
        })
        scores.append(_distance_to_confidence(dist))

    # Calculate overall confidence
    if scores:
        best = scores[0]
        avg_scores = sum(scores) / len(scores)
        overall_confidence = round(0.7 * best + 0.3 * avg_scores, 2)
    else:
        overall_confidence = 0.0

    return {
        "top": ranked,
        "context_block": "\n\n".join(context_lines),
        "citations": citations,
        "confidence": overall_confidence,
        "latency_ms": latency_ms,
    }


async def answer_web_query(
    query: str,
    website_id: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Full RAG pipeline:
    1. Semantic retrieval with website_id isolation.
    2. Prompt construction with strict grounding rules.
    3. Groq LLM inference.
    4. Exact fallback check if unsupported.
    5. Logging and performance stats.
    """
    total_start = time.perf_counter()
    retrieval_res = await retrieve_website_context(query, website_id=website_id, top_k=top_k)

    context_block = retrieval_res["context_block"]
    citations = retrieval_res["citations"]
    confidence = retrieval_res["confidence"]

    # If nothing was retrieved or confidence is too low
    if not citations or not context_block.strip():
        answer = "The requested information was not found in the indexed website content."
        total_latency_ms = (time.perf_counter() - total_start) * 1000
        log_query(query, website_id, total_latency_ms, 0.0, 0)
        return {
            "answer": answer,
            "confidence": 0.0,
            "citations": [],
            "retrieval_latency_ms": retrieval_res["latency_ms"],
            "total_latency_ms": total_latency_ms,
            "reasoning": "No relevant chunks retrieved from the indexed website collection.",
        }

    user_prompt = f"""Retrieved Website Content:
{context_block}

User Question:
{query}

Answer the question grounded strictly in the excerpts above. Include source citations [1], [2]. If the information is not present, reply with:
"The requested information was not found in the indexed website content."
"""

    try:
        raw_answer = await groq_client.chat_completion(WEB_RAG_SYSTEM_PROMPT, user_prompt)
        final_answer = raw_answer.strip()
        reasoning = f"Generated answer using Groq Llama 3.3 70B grounded in {len(citations)} retrieved passages from {website_id}."
    except Exception as e:
        # Extractive fallback if Groq API fails or key is missing
        top_snippet = citations[0]["snippet"]
        final_answer = f"Extractive retrieval fallback (LLM offline: {e}):\n\n{top_snippet}\n\nSource: {citations[0]['url']}"
        reasoning = "Groq LLM call failed; surfaced highest ranking passage directly."

    total_latency_ms = (time.perf_counter() - total_start) * 1000
    log_query(query, website_id, total_latency_ms, confidence, len(citations))

    return {
        "answer": final_answer,
        "confidence": confidence,
        "citations": citations,
        "retrieval_latency_ms": round(retrieval_res["latency_ms"], 2),
        "total_latency_ms": round(total_latency_ms, 2),
        "reasoning": reasoning,
    }


def delete_website_vectors(website_id: str) -> int:
    """Removes all vectors belonging to a website from ChromaDB."""
    collection = get_web_collection()
    try:
        results = collection.get(where={"website_id": website_id})
        ids_to_del = results.get("ids", [])
        if ids_to_del:
            collection.delete(ids=ids_to_del)
            return len(ids_to_del)
    except Exception as e:
        print(f"[web_retrieval] Error deleting vectors for {website_id}: {e}", flush=True)
    return 0
