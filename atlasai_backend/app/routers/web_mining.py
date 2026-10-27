"""
FastAPI Router for WebRAG — Intelligent Website Mining & Question Answering System.

Endpoints:
- POST /api/web/crawl: Start website crawling and indexing in a background task.
- GET /api/web/status/{job_id}: Return crawling progress, status, and errors.
- GET /api/web/websites: Return catalog of all indexed websites.
- GET /api/web/pages: Return list of crawled pages for a given website.
- POST /api/web/chat: Ask grounded questions about indexed website content.
- GET /api/web/stats: Return mining statistics (word freq, distribution, latency, charts).
- DELETE /api/web/index/{website_id}: Delete a website's vectors and metadata.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
from typing import List, Optional
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.models.schemas import (
    WebChatRequest,
    WebChatResponse,
    WebCitationItem,
    WebCrawlRequest,
    WebCrawlResponse,
    WebJobStatusResponse,
    WebPageItem,
    WebStatsResponse,
    WebsiteSummaryItem,
)
from app.services import web_analytics, web_preprocessing, web_retrieval, web_store
from app.services.web_crawler import SSRFValidationError, WebCrawler, is_safe_url

router = APIRouter(prefix="/api/web", tags=["Web Mining & RAG"])
logger = logging.getLogger(__name__)


async def _run_crawl_and_index_task(
    job_id: str,
    website_id: str,
    url: str,
    max_pages: int,
    max_depth: int,
) -> None:
    """
    Background worker that runs crawling, text cleaning, chunking,
    embedding generation, and ChromaDB vector indexing.
    """
    try:
        web_store.update_job(job_id, status="crawling", progress=5)

        # Progress callback to update live job status
        def on_crawl_progress(count: int, max_pages: int, url: str, title: str):
            pct = min(75, int(10 + (count / max_pages) * 65))
            web_store.update_job(
                job_id,
                progress=pct,
                crawled_count=count,
                current_url=url,
                current_title=title,
            )

        crawler = WebCrawler(
            start_url=url,
            max_pages=max_pages,
            max_depth=max_depth,
            delay=0.25,
        )

        # Run crawler in thread to prevent blocking event loop
        crawled_pages = await asyncio.to_thread(crawler.crawl, on_crawl_progress)

        if not crawled_pages:
            web_store.update_job(
                job_id,
                status="failed",
                error="No readable content found or crawling was blocked by robots.txt / domain rules.",
            )
            return

        web_store.update_job(
            job_id,
            status="indexing",
            progress=80,
            crawled_count=len(crawled_pages),
        )

        seen_hashes = set()
        all_chunks = []
        catalog_pages = []
        total_words = 0

        for page in crawled_pages:
            processed = web_preprocessing.preprocess_webpage(
                page=page,
                website_id=website_id,
                chunk_size=700,
                overlap=150,
                seen_hashes=seen_hashes,
            )

            if processed["is_duplicate"]:
                continue

            all_chunks.extend(processed["chunks"])
            total_words += processed["word_count"]

            catalog_pages.append({
                "url": processed["url"],
                "title": processed["title"],
                "word_count": processed["word_count"],
                "chunk_count": len(processed["chunks"]),
                "language": processed["language"],
                "timestamp": processed["timestamp"],
                "content_hash": processed["content_hash"],
                "text": page.get("text", ""),
            })

        # Save pages to web store
        web_store.save_pages(website_id, catalog_pages)

        # Embed and insert chunks into ChromaDB
        if all_chunks:
            await web_retrieval.index_website_chunks(website_id, all_chunks)

        # Save website summary
        domain = urlparse(url).netloc
        web_store.save_website(website_id, {
            "website_id": website_id,
            "domain": domain,
            "start_url": url,
            "total_pages": len(catalog_pages),
            "total_chunks": len(all_chunks),
            "total_words": total_words,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
        })

        web_store.update_job(
            job_id,
            status="completed",
            progress=100,
            crawled_count=len(catalog_pages),
            current_url=f"Indexed {len(all_chunks)} chunks across {len(catalog_pages)} pages.",
        )

    except SSRFValidationError as e:
        logger.error("SSRF validation blocked %s: %s", url, e)
        web_store.update_job(job_id, status="failed", error=str(e))
    except Exception as e:
        logger.exception("Crawling failed for %s", url)
        web_store.update_job(job_id, status="failed", error=f"Crawling failed: {str(e)}")


@router.post("/crawl", response_model=WebCrawlResponse)
async def start_website_crawl(
    request: WebCrawlRequest,
    background_tasks: BackgroundTasks,
):
    """
    Validates website URL, protects against SSRF, and schedules background crawl and index job.
    """
    raw_url = request.url.strip()
    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url

    if not is_safe_url(raw_url):
        raise HTTPException(
            status_code=400,
            detail="Forbidden URL. Only public HTTP/HTTPS URLs are allowed. Localhost, loopback, and private IP ranges are blocked.",
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    domain = urlparse(raw_url).netloc
    website_id = f"site_{hashlib.md5(domain.encode()).hexdigest()[:8]}"

    web_store.create_job(
        job_id=job_id,
        website_id=website_id,
        start_url=raw_url,
        max_pages=request.max_pages or 30,
        max_depth=request.max_depth or 2,
    )

    background_tasks.add_task(
        _run_crawl_and_index_task,
        job_id=job_id,
        website_id=website_id,
        url=raw_url,
        max_pages=request.max_pages or 30,
        max_depth=request.max_depth or 2,
    )

    return WebCrawlResponse(
        jobId=job_id,
        websiteId=website_id,
        status="queued",
        message=f"Crawling job initiated for {raw_url} (Max {request.max_pages or 30} pages, Depth {request.max_depth or 2})",
    )


@router.get("/status/{job_id}", response_model=WebJobStatusResponse)
async def get_crawl_job_status(job_id: str):
    """Returns real-time progress and status of a crawling/indexing job."""
    job = web_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    return WebJobStatusResponse(
        jobId=job["job_id"],
        websiteId=job["website_id"],
        startUrl=job["start_url"],
        status=job["status"],
        progress=job["progress"],
        crawledCount=job["crawled_count"],
        maxPages=job["max_pages"],
        currentUrl=job.get("current_url"),
        currentTitle=job.get("current_title"),
        error=job.get("error"),
    )


@router.get("/websites", response_model=List[WebsiteSummaryItem])
async def list_indexed_websites():
    """Lists all successfully crawled and indexed websites."""
    sites = web_store.list_websites()
    return [
        WebsiteSummaryItem(
            websiteId=s["website_id"],
            domain=s["domain"],
            startUrl=s["start_url"],
            totalPages=s["total_pages"],
            totalChunks=s["total_chunks"],
            totalWords=s["total_words"],
            createdAt=s["created_at"],
            status=s["status"],
        )
        for s in sites
    ]


@router.get("/pages", response_model=List[WebPageItem])
async def list_indexed_pages(website_id: str = Query(..., description="Website ID to list pages for")):
    """Returns the list of indexed pages for a given website."""
    pages = web_store.get_pages(website_id)
    return [
        WebPageItem(
            url=p["url"],
            title=p["title"],
            wordCount=p["word_count"],
            chunkCount=p["chunk_count"],
            language=p.get("language", "English"),
            timestamp=p.get("timestamp", ""),
        )
        for p in pages
    ]


@router.post("/chat", response_model=WebChatResponse)
async def ask_website_question(request: WebChatRequest):
    """
    Executes top-k semantic search strictly on the requested website's ChromaDB vectors
    and generates an answer grounded strictly in the retrieved excerpts.
    """
    if not request.website_id:
        raise HTTPException(status_code=400, detail="website_id is required.")
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    result = await web_retrieval.answer_web_query(
        query=request.query.strip(),
        website_id=request.website_id,
        top_k=request.top_k or 5,
    )

    citations_out = [
        WebCitationItem(
            index=c["index"],
            url=c["url"],
            title=c["title"],
            snippet=c["snippet"],
            distance=c.get("distance"),
        )
        for c in result["citations"]
    ]

    return WebChatResponse(
        websiteId=request.website_id,
        query=request.query,
        answer=result["answer"],
        confidence=result["confidence"],
        citations=citations_out,
        retrievalLatencyMs=result["retrieval_latency_ms"],
        totalLatencyMs=result["total_latency_ms"],
        reasoning=result["reasoning"],
    )


@router.get("/stats", response_model=WebStatsResponse)
async def get_web_statistics(website_id: Optional[str] = Query(None, description="Optional website ID filter")):
    """
    Returns web data mining statistics (word counts, chunk numbers, top keywords,
    word count distribution, retrieval latency) and base64 chart images.
    """
    stats = web_analytics.get_web_mining_statistics(website_id)

    return WebStatsResponse(
        websiteId=stats["website_id"],
        totalWebsites=stats["total_websites"],
        totalPages=stats["total_pages"],
        totalWords=stats["total_words"],
        totalChunks=stats["total_chunks"],
        averageWordsPerPage=stats["average_words_per_page"],
        topWords=stats["top_words"],
        contentDistribution=stats["content_distribution"],
        averageRetrievalLatencyMs=stats["average_retrieval_latency_ms"],
        averageConfidence=stats["average_confidence"],
        totalQueriesLogged=stats["total_queries_logged"],
        wordFrequencyChartBase64=stats.get("word_frequency_chart_base64", ""),
        contentDistributionChartBase64=stats.get("content_distribution_chart_base64", ""),
    )


@router.delete("/index/{website_id}")
async def delete_website_index(website_id: str):
    """
    Deletes all indexed vectors and catalog entries for a website.
    """
    vectors_deleted = web_retrieval.delete_website_vectors(website_id)
    removed_from_store = web_store.delete_website(website_id)

    if not removed_from_store and vectors_deleted == 0:
        raise HTTPException(status_code=404, detail=f"Website {website_id} not found.")

    return {
        "websiteId": website_id,
        "deleted": True,
        "vectorsDeleted": vectors_deleted,
        "message": f"Successfully deleted website index and {vectors_deleted} vector embeddings.",
    }
