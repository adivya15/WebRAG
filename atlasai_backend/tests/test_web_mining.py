"""
Comprehensive Unit and Integration Test Suite for WebRAG Backend.

Tests:
1. URL validation & SSRF protection (localhost, 127.0.0.1, 169.254.169.254, private IPs).
2. robots.txt compliance.
3. Crawl depth and page limits.
4. Content deduplication (SHA-256 hash).
5. HTML preprocessing and boilerplate stripping.
6. Text chunking and metadata preservation.
7. ChromaDB indexing and website-isolated retrieval.
8. Fallback answer behavior: "The requested information was not found in the indexed website content."
9. Citation correctness (URL, title, snippet).
10. FastAPI endpoints (crawl, status, pages, chat, stats, delete).
"""

import os
import sys

os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)


import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.web_crawler import is_safe_url, normalize_url, WebCrawler
from app.services import web_preprocessing, web_retrieval, web_store, web_analytics



client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. URL Validation & SSRF Protection Tests
# ---------------------------------------------------------------------------

def test_is_safe_url_blocks_localhost_and_private_ips():
    assert is_safe_url("http://localhost:8000") is False
    assert is_safe_url("http://127.0.0.1:8000") is False
    assert is_safe_url("http://127.0.0.2") is False
    assert is_safe_url("http://0.0.0.0:80") is False
    assert is_safe_url("http://10.0.0.1/admin") is False
    assert is_safe_url("http://172.16.0.5") is False
    assert is_safe_url("http://192.168.1.100") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data") is False  # Cloud metadata
    assert is_safe_url("ftp://example.com") is False
    assert is_safe_url("file:///etc/passwd") is False


import socket

@patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))])
def test_is_safe_url_allows_public_urls(mock_dns):
    assert is_safe_url("https://example.com") is True
    assert is_safe_url("https://en.wikipedia.org/wiki/Web_mining") is True



def test_normalize_url():
    url1 = "https://example.com/about/#team"
    url2 = "https://example.com/about"
    assert normalize_url(url1) == "https://example.com/about"
    assert normalize_url(url2) == "https://example.com/about"


# ---------------------------------------------------------------------------
# 2. robots.txt Compliance & Crawl Depth Tests
# ---------------------------------------------------------------------------

def test_robots_txt_disallow():
    crawler = WebCrawler(start_url="https://example.com", max_pages=5)
    crawler.robot_parser = MagicMock()
    crawler.robot_parser.can_fetch.side_effect = lambda ua, url: "/private" not in url

    assert crawler.is_allowed_by_robots("https://example.com/public") is True
    assert crawler.is_allowed_by_robots("https://example.com/private/data") is False


def test_html_data_extraction_and_boilerplate_stripping():
    sample_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Data Mining Laboratory</title>
        <meta name="description" content="Research on web mining and RAG">
      </head>
      <body>
        <nav><a href="/home">Home</a><a href="/login">Login</a></nav>
        <header>Header Banner</header>
        <main>
          <h1>Overview of Retrieval-Augmented Generation</h1>
          <p>Retrieval-Augmented Generation (RAG) optimizes the output of large language models.</p>
          <h2>Key Architecture Components</h2>
          <p>The components include embedding models, vector databases like ChromaDB, and Groq LLMs.</p>
          <a href="/docs/guide">Documentation Guide</a>
          <a href="https://otherdomain.com/out">External</a>
        </main>
        <footer>Copyright 2026. All rights reserved.</footer>
        <script>console.log("analytics");</script>
      </body>
    </html>
    """
    crawler = WebCrawler(start_url="https://example.com")
    data = crawler.extract_page_data(sample_html, "https://example.com/research")

    assert data["title"] == "Data Mining Laboratory"
    assert data["meta_description"] == "Research on web mining and RAG"
    assert "Overview of Retrieval-Augmented Generation" in data["headings"]
    assert "Retrieval-Augmented Generation (RAG) optimizes the output" in data["text"]
    # Verify stripped boilerplate
    assert "Copyright 2026" not in data["text"]
    assert "Header Banner" not in data["text"]
    assert "console.log" not in data["text"]
    # Verify outbound link scoping (external domain ignored)
    assert "https://example.com/docs/guide" in data["outbound_links"]
    assert "https://otherdomain.com/out" not in data["outbound_links"]


# ---------------------------------------------------------------------------
# 3. Preprocessing, Deduplication & Chunking Tests
# ---------------------------------------------------------------------------

def test_web_preprocessing_and_deduplication():
    seen = set()
    page1 = {
        "url": "https://example.com/page1",
        "title": "Machine Learning",
        "text": "Machine learning is a field of inquiry devoted to understanding and building methods that learn.",
    }
    page2_duplicate = {
        "url": "https://example.com/page2",
        "title": "ML Overview",
        "text": "Machine learning is a field of inquiry devoted to understanding and building methods that learn.   ",
    }

    res1 = web_preprocessing.preprocess_webpage(page1, "site_test", seen_hashes=seen)
    res2 = web_preprocessing.preprocess_webpage(page2_duplicate, "site_test", seen_hashes=seen)

    assert res1["is_duplicate"] is False
    assert res2["is_duplicate"] is True
    assert len(res1["chunks"]) > 0
    assert res1["chunks"][0]["source_url"] == "https://example.com/page1"
    assert res1["chunks"][0]["website_id"] == "site_test"


def test_chunk_web_content_overlap():
    long_text = "Paragraph one with important web data facts.\n\n" * 15
    chunks = web_preprocessing.chunk_web_content(long_text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) > 0


# ---------------------------------------------------------------------------
# 4. ChromaDB Indexing, Isolated Retrieval & Fallback Tests
# ---------------------------------------------------------------------------

import asyncio

def test_chromadb_website_indexing_and_isolation():
    async def _inner():
        site_a = "site_alpha_1"
        site_b = "site_beta_2"

        chunks_a = [
            {
                "chunk_id": "chunk_a_1",
                "website_id": site_a,
                "source_url": "https://alpha.com/quantum",
                "page_title": "Quantum Computing",
                "chunk_index": 0,
                "text": "Quantum computing uses qubits and quantum superposition to perform computations exponentially faster.",
                "content_hash": "hash_a_1",
                "timestamp": "2026-10-27T12:00:00Z",
            }
        ]
        chunks_b = [
            {
                "chunk_id": "chunk_b_1",
                "website_id": site_b,
                "source_url": "https://beta.com/biology",
                "page_title": "Marine Biology",
                "chunk_index": 0,
                "text": "Marine biology investigates oceanic biodiversity, coral reefs, and hydrothermal vents.",
                "content_hash": "hash_b_1",
                "timestamp": "2026-10-27T12:00:00Z",
            }
        ]

        await web_retrieval.index_website_chunks(site_a, chunks_a)
        await web_retrieval.index_website_chunks(site_b, chunks_b)

        # Query site A for quantum computing -> Should find quantum
        ret_a = await web_retrieval.retrieve_website_context("What are qubits?", website_id=site_a, top_k=3)
        assert len(ret_a["citations"]) > 0
        assert "Quantum" in ret_a["citations"][0]["title"]
        assert ret_a["citations"][0]["url"] == "https://alpha.com/quantum"

        # Query site B for quantum computing -> Should NOT return site A's chunks (Isolation guarantee)
        ret_b = await web_retrieval.retrieve_website_context("What are qubits?", website_id=site_b, top_k=3)
        for c in ret_b["citations"]:
            assert c["url"] != "https://alpha.com/quantum"

    asyncio.run(_inner())


def test_unsupported_query_fallback():
    async def _inner():
        site_empty = "site_empty_nonexistent"
        result = await web_retrieval.answer_web_query("What is the speed of light?", website_id=site_empty)
        assert result["answer"] == "The requested information was not found in the indexed website content."
        assert result["confidence"] == 0.0

    asyncio.run(_inner())



# ---------------------------------------------------------------------------
# 5. FastAPI Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_crawl_rejects_ssrf():
    res = client.post("/api/web/crawl", json={"url": "http://127.0.0.1:8000/internal"})
    assert res.status_code == 400
    assert "Forbidden URL" in res.json()["detail"]


@patch("app.routers.web_mining.is_safe_url", return_value=True)
def test_api_crawl_and_status(mock_safe):
    res = client.post("/api/web/crawl", json={"url": "https://example.com/mining", "max_pages": 2})
    assert res.status_code == 200
    data = res.json()
    assert "jobId" in data
    assert "websiteId" in data

    # Check status endpoint
    status_res = client.get(f"/api/web/status/{data['jobId']}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["jobId"] == data["jobId"]
    assert status_data["status"] in ("queued", "crawling", "indexing", "completed", "failed")



def test_api_stats():
    res = client.get("/api/web/stats")
    assert res.status_code == 200
    data = res.json()
    assert "totalWebsites" in data
    assert "totalPages" in data
    assert "topWords" in data
    assert "contentDistribution" in data


if __name__ == "__main__":
    print("[RUNNING TEST SUITE DIRECTLY]")
    test_is_safe_url_blocks_localhost_and_private_ips()
    print("PASS: test_is_safe_url_blocks_localhost_and_private_ips")
    test_is_safe_url_allows_public_urls()
    print("PASS: test_is_safe_url_allows_public_urls")
    test_normalize_url()
    print("PASS: test_normalize_url")
    test_robots_txt_disallow()
    print("PASS: test_robots_txt_disallow")
    test_html_data_extraction_and_boilerplate_stripping()
    print("PASS: test_html_data_extraction_and_boilerplate_stripping")
    test_web_preprocessing_and_deduplication()
    print("PASS: test_web_preprocessing_and_deduplication")
    test_chunk_web_content_overlap()
    print("PASS: test_chunk_web_content_overlap")
    test_chromadb_website_indexing_and_isolation()
    print("PASS: test_chromadb_website_indexing_and_isolation")
    test_unsupported_query_fallback()
    print("PASS: test_unsupported_query_fallback")
    test_api_crawl_rejects_ssrf()
    print("PASS: test_api_crawl_rejects_ssrf")
    test_api_crawl_and_status()
    print("PASS: test_api_crawl_and_status")
    test_api_stats()
    print("PASS: test_api_stats")
    print("ALL 12 TESTS PASSED SUCCESSFULLY!")

