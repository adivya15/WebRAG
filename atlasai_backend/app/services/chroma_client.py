import os
import chromadb

_client = None
_documents_collection = None


def get_client():
    global _client

    if _client is None:
        db_path = os.getenv("CHROMA_DB_PATH", "./chroma_db")

        _client = chromadb.PersistentClient(
            path=db_path
        )

    return _client


def get_documents_collection():
    global _documents_collection

    if _documents_collection is None:
        # Explicit on purpose. Without this, Chroma silently uses its
        # default HNSW space ("l2", i.e. squared Euclidean distance),
        # leaving retrieval.py's distance-to-cosine-similarity
        # conversion dependent on an unstated default instead of a
        # guaranteed contract. "cosine" matches the embedding model's
        # own name (multi-qa-MiniLM-L6-cos-v1) and is what
        # retrieval.py now assumes.
        #
        # IMPORTANT: this only affects a NEWLY created collection.
        # Chroma's HNSW index bakes in its distance metric at creation
        # time and does not change it for an existing collection, even
        # if you edit this line — if you already have ingested
        # documents in ./chroma_db, delete that folder (or just the
        # "documents" collection within it) and re-ingest everything
        # after this change, or the metric will silently stay whatever
        # it was before.
        _documents_collection = get_client().get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )

    return _documents_collection


_web_collection = None


def get_web_collection():
    """ChromaDB collection dedicated to crawled website content."""
    global _web_collection
    if _web_collection is None:
        _web_collection = get_client().get_or_create_collection(
            name="web_documents",
            metadata={"hnsw:space": "cosine"},
        )
    return _web_collection

