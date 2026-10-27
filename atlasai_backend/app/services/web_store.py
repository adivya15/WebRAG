"""
In-memory and persistent store for WebRAG crawled websites, background jobs, and page inventories.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

_lock = threading.Lock()

# Jobs dictionary: job_id -> { status, progress, current_url, crawled_count, max_pages, error, website_id, ... }
_jobs: Dict[str, Dict[str, Any]] = {}

# Websites registry: website_id -> { website_id, start_url, domain, total_pages, total_chunks, total_words, timestamp, ... }
_websites: Dict[str, Dict[str, Any]] = {}

# Pages catalog: website_id -> List[{ url, title, word_count, chunk_count, language, timestamp, content_hash }]
_pages_by_website: Dict[str, List[Dict[str, Any]]] = {}

# Query latency logs: List[{ query, website_id, latency_ms, timestamp, num_results, confidence }]
_query_logs: List[Dict[str, Any]] = []


def create_job(job_id: str, website_id: str, start_url: str, max_pages: int, max_depth: int) -> Dict[str, Any]:
    with _lock:
        job = {
            "job_id": job_id,
            "website_id": website_id,
            "start_url": start_url,
            "max_pages": max_pages,
            "max_depth": max_depth,
            "status": "queued",  # queued | crawling | indexing | completed | failed
            "progress": 0,       # 0 to 100
            "crawled_count": 0,
            "current_url": start_url,
            "current_title": "",
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _jobs[job_id] = job
        return dict(job)


def update_job(job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    with _lock:
        if job_id not in _jobs:
            return None
        job = _jobs[job_id]
        for k, v in kwargs.items():
            job[k] = v
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(job)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def save_website(website_id: str, website_data: Dict[str, Any]) -> None:
    with _lock:
        _websites[website_id] = website_data


def get_website(website_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        w = _websites.get(website_id)
        return dict(w) if w else None


def list_websites() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(w) for w in _websites.values()]


def save_pages(website_id: str, pages: List[Dict[str, Any]]) -> None:
    with _lock:
        _pages_by_website[website_id] = pages


def get_pages(website_id: str) -> List[Dict[str, Any]]:
    with _lock:
        return [dict(p) for p in _pages_by_website.get(website_id, [])]


def delete_website(website_id: str) -> bool:
    with _lock:
        removed = False
        if website_id in _websites:
            del _websites[website_id]
            removed = True
        if website_id in _pages_by_website:
            del _pages_by_website[website_id]
            removed = True
        return removed


def log_query(query: str, website_id: str, latency_ms: float, confidence: float, num_results: int) -> None:
    with _lock:
        _query_logs.append({
            "query": query,
            "website_id": website_id,
            "latency_ms": round(latency_ms, 2),
            "confidence": round(confidence, 2),
            "num_results": num_results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def get_query_logs(website_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with _lock:
        if website_id:
            return [l for l in _query_logs if l["website_id"] == website_id]
        return list(_query_logs)
