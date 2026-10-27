"""
Web Preprocessing Pipeline for WebRAG.

Features:
- Unicode normalization (NFKC).
- HTML/whitespace cleaning and boilerplate strip.
- Content hashing for exact and near-duplicate detection.
- Language identification (English, Marathi, Hindi, etc.).
- Text chunking with configurable size and overlap (500–800 chars/tokens),
  respecting sentence and paragraph boundaries.
- Preserves metadata: website_id, source_url, page_title, chunk_index, hash, timestamp.
"""

from datetime import datetime, timezone
import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set


def normalize_unicode(text: str) -> str:
    """Normalizes Unicode text to NFKC to standardize accented characters and ligatures."""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def clean_web_text(raw_text: str) -> str:
    """
    Cleans raw webpage text:
    - Normalizes unicode
    - Removes zero-width characters and control codes
    - Normalizes multiple spaces and tabs into single spaces
    - Collapses 3+ consecutive newlines into 2
    """
    if not raw_text:
        return ""

    text = normalize_unicode(raw_text)

    # Strip zero-width characters
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)

    # Replace non-breaking spaces with standard space
    text = text.replace("\u00A0", " ").replace("\u202F", " ")

    # Normalize horizontal whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Normalize excessive newlines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def compute_content_hash(text: str) -> str:
    """Computes SHA-256 hash of normalized text for deduplication."""
    cleaned = re.sub(r"\s+", "", text.lower())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def detect_page_language(text: str) -> str:
    """
    Detects predominant language using script character analysis.
    Supports English, Marathi/Hindi (Devanagari), and other scripts.
    """
    sample = text[:2000]
    devanagari_count = len(re.findall(r"[\u0900-\u097F]", sample))
    latin_count = len(re.findall(r"[A-Za-z]", sample))

    if devanagari_count > latin_count * 0.4:
        # Check specific Marathi indicator postpositions
        if any(w in sample for w in ["आहे", "नाही", "शासन", "निर्णय", "विद्यापीठ"]):
            return "Marathi"
        return "Hindi"

    return "English"


def chunk_web_content(
    text: str,
    chunk_size: int = 700,
    overlap: int = 150,
) -> List[str]:
    """
    Splits text into coherent chunks of target size with overlap.
    Attempts to break on paragraph boundaries (\n\n) or sentence boundaries (. ! ? \n).
    """
    cleaned = clean_web_text(text)
    if not cleaned:
        return []

    if len(cleaned) <= chunk_size:
        return [cleaned]

    # Split into paragraphs first
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

    chunks: List[str] = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{para}".strip()
        else:
            # If current chunk has content, save it
            if current_chunk:
                chunks.append(current_chunk)
                # Keep end of previous chunk as overlap
                words = current_chunk.split()
                overlap_words = words[-max(1, overlap // 7):]
                current_chunk = " ".join(overlap_words)

            # If the paragraph itself is huge, split it by sentence
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?\n])\s+", para)
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(current_chunk) + len(sent) + 1 <= chunk_size:
                        current_chunk = f"{current_chunk} {sent}".strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sent
            else:
                current_chunk = f"{current_chunk}\n\n{para}".strip()

    if current_chunk and current_chunk not in chunks:
        chunks.append(current_chunk)

    return chunks


def preprocess_webpage(
    page: Dict[str, Any],
    website_id: str,
    chunk_size: int = 700,
    overlap: int = 150,
    seen_hashes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Takes a crawled page dictionary, cleans the content, detects language,
    deduplicates against seen hashes, and chunks the text with full metadata preservation.
    """
    raw_text = page.get("text", "")
    content_hash = compute_content_hash(raw_text)

    is_duplicate = False
    if seen_hashes is not None:
        if content_hash in seen_hashes:
            is_duplicate = True
        else:
            seen_hashes.add(content_hash)

    clean_text = clean_web_text(raw_text)
    lang = detect_page_language(clean_text)
    chunks_text = chunk_web_content(clean_text, chunk_size=chunk_size, overlap=overlap)

    timestamp = datetime.now(timezone.utc).isoformat()
    url = page.get("url", "")
    title = page.get("title", "Untitled Page")

    structured_chunks: List[Dict[str, Any]] = []
    for idx, c_text in enumerate(chunks_text):
        chunk_id = f"web_{website_id[:8]}_{content_hash[:8]}_c{idx}"
        structured_chunks.append({
            "chunk_id": chunk_id,
            "website_id": website_id,
            "source_url": url,
            "page_title": title,
            "chunk_index": idx,
            "text": c_text,
            "content_hash": content_hash,
            "language": lang,
            "timestamp": timestamp,
        })

    return {
        "website_id": website_id,
        "url": url,
        "title": title,
        "canonical_url": page.get("canonical_url", url),
        "headings": page.get("headings", []),
        "meta_description": page.get("meta_description", ""),
        "language": lang,
        "word_count": len(clean_text.split()),
        "content_hash": content_hash,
        "is_duplicate": is_duplicate,
        "timestamp": timestamp,
        "chunks": structured_chunks,
    }
