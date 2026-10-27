"""
WebRAG Quantitative Evaluation Module.

Measures:
- Precision@k (for k=1, 3, 5)
- Recall@k (for k=1, 3, 5)
- Mean Reciprocal Rank (MRR)
- Retrieval latency (ms)
- Answer Correctness (token overlap & lexical alignment against reference ground truth)

Executes on actual indexed chunks in ChromaDB and produces a reproducible evaluation report.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Set

# Ensure backend root is on sys.path
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from app.services import embeddings, web_retrieval
from app.services.chroma_client import get_web_collection

# Standard evaluation corpus documents
EVAL_WEBSITE_ID = "eval_webrag_benchmark"
EVAL_CORPUS = [
    {
        "url": "https://webrag-benchmark.org/web-mining-overview",
        "title": "Web Data Mining Taxonomy",
        "text": """Web data mining is the application of data mining techniques to extract patterns and knowledge from web data.
It is categorized into three primary subdisciplines:
1. Web Content Mining: Extracting useful information from webpage contents such as text, images, and audio.
2. Web Structure Mining: Modeling the underlying link architecture and hyperlink topology (e.g., PageRank and HITS algorithms).
3. Web Usage Mining: Analyzing user behavioral data, clickstreams, server web logs, and browsing patterns to understand user interactions.
Web crawlers form the foundational data acquisition layer for both content and structure mining systems.""",
    },
    {
        "url": "https://webrag-benchmark.org/crawler-architecture",
        "title": "Web Crawler Politeness and Security",
        "text": """Autonomous web crawlers must adhere to ethical crawling standards and network security protocols.
Key crawler requirements include:
- robots.txt compliance: Parsed via standard robot exclusion rules before requesting any website paths.
- Rate limiting: Implementing politeness delays (typically 250ms to 500ms) between successive requests to prevent server denial-of-service.
- SSRF prevention: Validating all target URLs and blocking loopback addresses (127.0.0.1), private RFC1918 subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), and cloud metadata endpoints (169.254.169.254).
- Crawl limits: Enforcing maximum crawl depth and page count thresholds to prevent infinite traversal traps.""",
    },
    {
        "url": "https://webrag-benchmark.org/rag-pipeline",
        "title": "Retrieval-Augmented Generation Architecture",
        "text": """Retrieval-Augmented Generation (RAG) combines dense semantic retrieval with generative large language models.
In modern RAG pipelines:
1. Text Preprocessing: Normalizing Unicode (NFKC), stripping boilerplate HTML tags (nav, footer, script), and chunking text into 500-800 character windows with sentence-boundary preservation.
2. Dense Embedding: Converting text passages into high-dimensional vector representations using bi-encoder models such as multi-qa-MiniLM-L6-cos-v1.
3. Vector Indexing: Storing vectors in an HNSW-indexed vector database like ChromaDB using cosine distance metrics.
4. Grounded Synthesis: Passing retrieved top-k passages into an LLM with strict negative constraint prompting to eliminate hallucinations.""",
    },
    {
        "url": "https://webrag-benchmark.org/vector-search",
        "title": "Vector Databases and Semantic Similarity",
        "text": """ChromaDB serves as an open-source persistent vector store for dense retrieval.
Cosine distance is defined as d = 1 - cos_sim(u, v), where cos_sim is the normalized dot product between query and passage vectors.
Using cosine distance ensures scale-invariant similarity comparisons across varying text lengths.
Metadata filtering partitioned by website_id guarantees tenant isolation, preventing cross-domain retrieval contamination.""",
    },
    {
        "url": "https://webrag-benchmark.org/evaluation-metrics",
        "title": "Information Retrieval Evaluation Metrics",
        "text": """Standard metrics for evaluating RAG retrieval systems include:
- Precision@k: The fraction of retrieved documents in the top-k results that are relevant.
- Recall@k: The fraction of all relevant documents that are successfully retrieved in the top-k.
- Mean Reciprocal Rank (MRR): The average of reciprocal ranks (1/rank) of the first relevant document across all evaluation queries.
- Retrieval Latency: The execution time required to embed the query and fetch top-k nearest neighbors, typically measured in milliseconds.""",
    },
]

# Evaluation questions with ground truth relevant URLs and reference answers
EVAL_DATASET = [
    {
        "query": "What are the three main categories of web data mining?",
        "relevant_urls": ["https://webrag-benchmark.org/web-mining-overview"],
        "expected_answer_keywords": ["content mining", "structure mining", "usage mining"],
    },
    {
        "query": "How do web crawlers prevent SSRF vulnerabilities and respect website rules?",
        "relevant_urls": ["https://webrag-benchmark.org/crawler-architecture"],
        "expected_answer_keywords": ["robots.txt", "ssrf", "private", "metadata", "rate limiting"],
    },
    {
        "query": "What are the core stages in a website RAG pipeline?",
        "relevant_urls": ["https://webrag-benchmark.org/rag-pipeline"],
        "expected_answer_keywords": ["preprocessing", "embedding", "vector", "chromadb", "retrieval"],
    },
    {
        "query": "Why is cosine distance used in ChromaDB for semantic retrieval?",
        "relevant_urls": ["https://webrag-benchmark.org/vector-search"],
        "expected_answer_keywords": ["cosine", "similarity", "normalized", "isolation"],
    },
    {
        "query": "How are Precision@k, Recall@k, and MRR defined for search evaluation?",
        "relevant_urls": ["https://webrag-benchmark.org/evaluation-metrics"],
        "expected_answer_keywords": ["precision", "recall", "mrr", "reciprocal rank"],
    },
]


def compute_token_overlap_score(candidate: str, expected_keywords: List[str]) -> float:
    """Computes keyword coverage of candidate text against expected reference keywords."""
    candidate_lower = candidate.lower()
    matches = sum(1 for kw in expected_keywords if kw.lower() in candidate_lower)
    return round(matches / max(1, len(expected_keywords)), 2)


async def setup_eval_corpus() -> int:
    """Indexes the benchmark corpus into ChromaDB."""
    all_chunks = []
    for doc in EVAL_CORPUS:
        chunks = [doc["text"]]
        for idx, c in enumerate(chunks):
            all_chunks.append({
                "chunk_id": f"eval_{idx}_{abs(hash(doc['url'])) % 10000}",
                "website_id": EVAL_WEBSITE_ID,
                "source_url": doc["url"],
                "page_title": doc["title"],
                "chunk_index": idx,
                "text": c,
                "content_hash": str(hash(c)),
                "language": "English",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # Clear previous eval vectors if any
    web_retrieval.delete_website_vectors(EVAL_WEBSITE_ID)
    indexed_count = await web_retrieval.index_website_chunks(EVAL_WEBSITE_ID, all_chunks)
    return indexed_count


async def run_evaluation() -> Dict[str, Any]:
    print("=" * 60)
    print("WebRAG Quantitative Evaluation Benchmark")
    print("=" * 60)
    print("Setting up evaluation benchmark corpus...")
    indexed = await setup_eval_corpus()
    print(f"Indexed {indexed} chunks in ChromaDB for website_id: {EVAL_WEBSITE_ID}")

    results = []
    p_at_1_list, p_at_3_list, p_at_5_list = [], [], []
    r_at_1_list, r_at_3_list, r_at_5_list = [], [], []
    rr_list = []
    latencies = []
    correctness_scores = []

    for item in EVAL_DATASET:
        query = item["query"]
        relevant_urls = set(item["relevant_urls"])

        # Measure retrieval metrics at top_k=5
        t0 = time.perf_counter()
        retrieval_res = await web_retrieval.retrieve_website_context(
            query=query,
            website_id=EVAL_WEBSITE_ID,
            top_k=5,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        retrieved_citations = retrieval_res["citations"]
        retrieved_urls = [c["url"] for c in retrieved_citations]

        # Precision & Recall @ k
        def precision_at_k(k: int) -> float:
            top_k_urls = retrieved_urls[:k]
            if not top_k_urls:
                return 0.0
            hits = sum(1 for u in top_k_urls if u in relevant_urls)
            return hits / k

        def recall_at_k(k: int) -> float:
            top_k_urls = set(retrieved_urls[:k])
            hits = len(top_k_urls.intersection(relevant_urls))
            return hits / len(relevant_urls)

        p1, p3, p5 = precision_at_k(1), precision_at_k(3), precision_at_k(5)
        r1, r3, r5 = recall_at_k(1), recall_at_k(3), recall_at_k(5)

        p_at_1_list.append(p1)
        p_at_3_list.append(p3)
        p_at_5_list.append(p5)
        r_at_1_list.append(r1)
        r_at_3_list.append(r3)
        r_at_5_list.append(r5)

        # Reciprocal Rank (RR)
        rr = 0.0
        for rank, u in enumerate(retrieved_urls, start=1):
            if u in relevant_urls:
                rr = 1.0 / rank
                break
        rr_list.append(rr)

        # Answer Correctness
        answer_res = await web_retrieval.answer_web_query(
            query=query,
            website_id=EVAL_WEBSITE_ID,
            top_k=3,
        )
        correctness = compute_token_overlap_score(answer_res["answer"], item["expected_answer_keywords"])
        correctness_scores.append(correctness)

        results.append({
            "query": query,
            "relevant_urls": list(relevant_urls),
            "retrieved_urls": retrieved_urls[:3],
            "p@1": p1,
            "p@3": round(p3, 2),
            "p@5": round(p5, 2),
            "r@1": r1,
            "r@3": round(r3, 2),
            "r@5": round(r5, 2),
            "rr": round(rr, 2),
            "latency_ms": round(latency_ms, 2),
            "answer_correctness": correctness,
            "answer_preview": answer_res["answer"][:120] + "...",
        })

    mrr = sum(rr_list) / len(rr_list)
    mean_p1 = sum(p_at_1_list) / len(p_at_1_list)
    mean_p3 = sum(p_at_3_list) / len(p_at_3_list)
    mean_p5 = sum(p_at_5_list) / len(p_at_5_list)
    mean_r1 = sum(r_at_1_list) / len(r_at_1_list)
    mean_r3 = sum(r_at_3_list) / len(r_at_3_list)
    mean_r5 = sum(r_at_5_list) / len(r_at_5_list)
    avg_latency = sum(latencies) / len(latencies)
    avg_correctness = sum(correctness_scores) / len(correctness_scores)

    summary = {
        "benchmark_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_test_queries": len(EVAL_DATASET),
        "mean_precision_at_1": round(mean_p1, 3),
        "mean_precision_at_3": round(mean_p3, 3),
        "mean_precision_at_5": round(mean_p5, 3),
        "mean_recall_at_1": round(mean_r1, 3),
        "mean_recall_at_3": round(mean_r3, 3),
        "mean_recall_at_5": round(mean_r5, 3),
        "mean_reciprocal_rank_mrr": round(mrr, 3),
        "average_retrieval_latency_ms": round(avg_latency, 2),
        "average_answer_correctness": round(avg_correctness, 3),
        "query_results": results,
    }

    report_path = os.path.join(backend_root, "evaluation", "evaluation_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS SUMMARY")
    print("=" * 60)
    print(f"Mean Reciprocal Rank (MRR):      {mrr:.3f}")
    print(f"Precision @ 1:                  {mean_p1:.3f}")
    print(f"Precision @ 3:                  {mean_p3:.3f}")
    print(f"Precision @ 5:                  {mean_p5:.3f}")
    print(f"Recall @ 1:                     {mean_r1:.3f}")
    print(f"Recall @ 3:                     {mean_r3:.3f}")
    print(f"Recall @ 5:                     {mean_r5:.3f}")
    print(f"Average Retrieval Latency:      {avg_latency:.2f} ms")
    print(f"Average Answer Correctness:     {avg_correctness:.3f} / 1.000")
    print(f"Report saved to: {report_path}")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    asyncio.run(run_evaluation())
