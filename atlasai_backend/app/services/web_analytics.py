"""
Web Data Mining Analytics and Visualizations for WebRAG.

Calculates:
1. Number of pages crawled.
2. Number of extracted words.
3. Number of generated chunks.
4. Top-K most frequent meaningful words (stopwords filtered).
5. Content distribution across pages (word count per page).
6. Average retrieval and end-to-end latency.
7. Base64-encoded Matplotlib charts for visual reporting:
   - Word Frequency Bar Chart
   - Content Distribution Histogram
"""

import base64
from collections import Counter
import io
import re
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive background rendering
import matplotlib.pyplot as plt

from app.services.chroma_client import get_web_collection
from app.services.web_store import get_pages, get_query_logs, get_website, list_websites

# English common stopwords
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd",
    "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves", "will", "also",
    "may", "one", "two", "use", "used", "new", "page", "site", "web", "information", "click",
}


def calculate_word_frequencies(pages: List[Dict[str, Any]], top_n: int = 15) -> List[Dict[str, Any]]:
    """Calculates most frequent non-stopword tokens from actual crawled page text."""
    counter = Counter()

    for p in pages:
        # Check text in page or headings/title
        text = p.get("text", "") or (p.get("title", "") + " " + p.get("meta_description", ""))
        tokens = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        meaningful_tokens = [w for w in tokens if w not in STOPWORDS]
        counter.update(meaningful_tokens)

    return [{"word": word, "count": count} for word, count in counter.most_common(top_n)]


def generate_word_freq_chart(word_freqs: List[Dict[str, Any]]) -> str:
    """Renders a horizontal bar chart of top words as a base64 PNG data URL."""
    if not word_freqs:
        return ""

    words = [item["word"] for item in reversed(word_freqs[:12])]
    counts = [item["count"] for item in reversed(word_freqs[:12])]

    plt.figure(figsize=(7, 4), dpi=120)
    plt.barh(words, counts, color="#2563EB", edgecolor="#1D4ED8", height=0.6)
    plt.title("Most Frequent Meaningful Words", fontsize=12, fontweight="bold", pad=12)
    plt.xlabel("Occurrences", fontsize=10)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"


def generate_distribution_chart(pages: List[Dict[str, Any]]) -> str:
    """Renders a distribution histogram of page word counts as a base64 PNG data URL."""
    word_counts = [p.get("word_count", 0) for p in pages if p.get("word_count", 0) > 0]
    if not word_counts:
        return ""

    plt.figure(figsize=(7, 4), dpi=120)
    plt.hist(word_counts, bins=min(10, max(3, len(word_counts))), color="#10B981", edgecolor="#059669")
    plt.title("Content Distribution (Word Count per Page)", fontsize=12, fontweight="bold", pad=12)
    plt.xlabel("Word Count", fontsize=10)
    plt.ylabel("Number of Pages", fontsize=10)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"


def get_web_mining_statistics(website_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes comprehensive web data mining metrics from actual stored data:
    - Total pages
    - Total words
    - Total chunks in ChromaDB
    - Top word frequencies
    - Content distribution per page
    - Retrieval latency stats
    - Base64 charts
    """
    if website_id:
        website = get_website(website_id)
        pages = get_pages(website_id)
        websites = [website] if website else []
    else:
        websites = list_websites()
        pages = []
        for w in websites:
            pages.extend(get_pages(w["website_id"]))

    total_pages = len(pages)
    total_words = sum(p.get("word_count", 0) for p in pages)

    # Chunks from ChromaDB collection
    web_col = get_web_collection()
    if website_id:
        try:
            res = web_col.get(where={"website_id": website_id})
            total_chunks = len(res.get("ids", []))
        except Exception:
            total_chunks = sum(p.get("chunk_count", 0) for p in pages)
    else:
        try:
            total_chunks = web_col.count()
        except Exception:
            total_chunks = sum(p.get("chunk_count", 0) for p in pages)

    # Word frequency analysis
    top_words = calculate_word_frequencies(pages, top_n=15)

    # Content distribution per page
    content_distribution = [
        {
            "url": p.get("url", ""),
            "title": p.get("title", "Untitled"),
            "word_count": p.get("word_count", 0),
            "chunk_count": p.get("chunk_count", 0),
        }
        for p in pages
    ]

    # Latency analytics from query logs
    query_logs = get_query_logs(website_id)
    if query_logs:
        avg_retrieval_latency = sum(q["latency_ms"] for q in query_logs) / len(query_logs)
        avg_confidence = sum(q["confidence"] for q in query_logs) / len(query_logs)
    else:
        avg_retrieval_latency = 0.0
        avg_confidence = 0.0

    # Generate charts
    word_freq_chart = generate_word_freq_chart(top_words)
    distribution_chart = generate_distribution_chart(pages)

    return {
        "website_id": website_id or "all",
        "total_websites": len(websites),
        "total_pages": total_pages,
        "total_words": total_words,
        "total_chunks": total_chunks,
        "average_words_per_page": round(total_words / total_pages, 1) if total_pages > 0 else 0,
        "top_words": top_words,
        "content_distribution": content_distribution,
        "average_retrieval_latency_ms": round(avg_retrieval_latency, 2),
        "average_confidence": round(avg_confidence, 2),
        "total_queries_logged": len(query_logs),
        "word_frequency_chart_base64": word_freq_chart,
        "content_distribution_chart_base64": distribution_chart,
    }
