"""
Embeddings — computed locally via sentence-transformers, not over the
network. The model is pre-downloaded into the Docker image at build
time (see Dockerfile), so there is zero network dependency at runtime.

This replaces the earlier HF Inference API approach, which was prone
to intermittent ConnectTimeout failures — dangerous for a live demo,
since a failed call silently degraded to a near-meaningless hash-based
embedding and tanked confidence scores unpredictably.

Same model as before (multi-qa-MiniLM-L6-cos-v1, tuned for asymmetric
question -> passage retrieval), same 384-dim output — this is a
drop-in replacement, nothing downstream (chroma_client.py,
knowledge_agent.py) needs to change.

FIX (Render free-tier OOM): main.py's ingest endpoint used to call
embed_batch() ONCE with every chunk from the whole document — for a
multi-page circular that's 30-50+ chunks encoded simultaneously,
spiking peak RAM right when a 512MB instance has the least headroom
(model + ChromaDB + FastAPI + the PDF bytes already in memory). This
now encodes in small batches internally instead, so peak memory is
bounded by BATCH_SIZE regardless of how large the document is. This
is the change directly, not a config flag — main.py's call site is
unchanged (still one embed_batch(docs) call); the batching happens
inside this function so nothing else needs to know about it.
"""
import os
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import asyncio
import gc
from typing import List

from sentence_transformers import SentenceTransformer


_model = None

# Chunks encoded per model.encode() call. Lower = less peak RAM, more
# Python-level overhead from more, smaller calls. 8 is a starting
# point for a 512MB instance — if you still see memory issues, try 4;
# if you upgrade off the free tier, this can go higher (16-32) for
# faster ingestion with no downside.
BATCH_SIZE = 8


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Already cached in the image from the Dockerfile RUN step,
        # so this just loads it into memory — no download happens here.
        _model = SentenceTransformer("sentence-transformers/multi-qa-MiniLM-L6-cos-v1")
    return _model


def _encode_sync(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    vectors: List[List[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_vectors = model.encode(
            batch, normalize_embeddings=True, convert_to_numpy=True
        )
        vectors.extend(vec.tolist() for vec in batch_vectors)
        # Drop the numpy batch result and ask the allocator to release
        # what it can before starting the next batch, instead of
        # letting every batch's intermediate tensors pile up until the
        # whole document is done.
        del batch_vectors
        gc.collect()
    return vectors


async def embed_batch(texts: List[str]) -> List[List[float]]:
    # encode() is CPU-bound and synchronous — run it in a worker thread
    # so it doesn't block the event loop while other requests are in flight.
    return await asyncio.to_thread(_encode_sync, texts)


async def embed(text: str) -> List[float]:
    result = await embed_batch([text])
    return result[0]