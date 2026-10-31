"""Stage 5 – Retrieval pipeline for matching candidate resumes with job postings.

Provides :func:`retrieve_matched_jobs`, which embeds a candidate's resume text
using `BAAI/bge-m3` and queries a persistent ChromaDB collection to retrieve
the most relevant job postings based on cosine similarity.

Design decisions
~~~~~~~~~~~~~~~~
* **Single model guarantee** – uses `settings.embedding_model_name` (default:
  `BAAI/bge-m3`) for both indexing and querying, guaranteeing embedding space alignment.
* **Cached model & client** – the 2.2 GB model and ChromaDB client are initialized
  once per process and cached, avoiding expensive reloads on every request.
* **Normalized cosine similarity** – distances returned by ChromaDB (cosine space)
  are converted into an intuitive similarity score in [0.0, 1.0] rounded to 4 decimals.
* **Graceful degradation** – returns an empty list if the vector database is empty
  or uninitialized, logging informative diagnostics rather than crashing.

Usage::

    from app.retrieval.retrieval import retrieve_matched_jobs

    matched = retrieve_matched_jobs(resume_text, top_k=5)
    # matched == [{"id": "...", "title": "...", "company": "...", ...}, ...]
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached singletons
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load and cache the sentence-transformers embedding model.

    Cached with lru_cache so the heavy model weights (BAAI/bge-m3) are loaded
    only once per worker process. The tokenizer window is aligned with the
    indexing side (``settings.embedding_max_seq_length``) so resume queries
    and job vectors are truncated identically.
    """
    settings = get_settings()
    logger.info("Loading embedding model '%s' ...", settings.embedding_model_name)
    try:
        model = SentenceTransformer(settings.embedding_model_name, local_files_only=True)
    except Exception:
        model = SentenceTransformer(settings.embedding_model_name)
    try:
        model.max_seq_length = settings.embedding_max_seq_length
    except Exception as exc:
        logger.warning("Could not set max_seq_length=%s: %s", settings.embedding_max_seq_length, exc)
    return model


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    """Return a cached ChromaDB PersistentClient."""
    settings = get_settings()
    chroma_dir = settings.resolved_chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Connecting to ChromaDB at: %s", chroma_dir)
    return chromadb.PersistentClient(path=str(chroma_dir))


@lru_cache(maxsize=1)
def get_hazm_normalizer():
    """Lazily load and cache the Hazm Persian normalizer."""
    try:
        from hazm import Normalizer
        return Normalizer()
    except Exception as exc:
        logger.warning("Hazm not available, proceeding without normalization: %s", exc)
        return None


def get_job_collection() -> chromadb.Collection | None:
    """Get the job postings collection from ChromaDB.

    Returns None if the collection does not exist yet (e.g. before indexing).
    """
    settings = get_settings()
    client = get_chroma_client()
    try:
        return client.get_collection(name=settings.chroma_collection_name)
    except Exception as exc:
        logger.warning(
            "Collection '%s' not found in ChromaDB: %s",
            settings.chroma_collection_name,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def retrieve_matched_jobs(
    resume_text: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve top-k job postings relevant to the given resume text.

    Parameters
    ----------
    resume_text:
        Raw or extracted text of the candidate's resume.
    top_k:
        Maximum number of matching job postings to return (default: 10).

    Returns
    -------
    list[dict[str, Any]]
        List of matched job dictionaries sorted by ``similarity_score`` descending:
        ``[{"id": str, "title": str, "company": str, "similarity_score": float,
           "source_url": str, "description_clean": str}, ...]``
    """
    # Guard against empty/whitespace input or non-positive top_k
    cleaned_resume = resume_text.strip()
    if not cleaned_resume or top_k <= 0:
        return []

    # Persian text normalization with Hazm (unifies yeh/kaf, ZWNJ, etc.)
    normalizer = get_hazm_normalizer()
    if normalizer is not None:
        try:
            cleaned_resume = normalizer.normalize(cleaned_resume)
        except Exception as exc:
            logger.warning("Hazm normalization failed: %s", exc)

    collection = get_job_collection()
    if collection is None:
        logger.error(
            "Cannot retrieve jobs: ChromaDB collection '%s' is not available.",
            get_settings().chroma_collection_name,
        )
        return []

    total_count = collection.count()
    if total_count == 0:
        logger.warning("ChromaDB collection is empty. Returning empty list.")
        return []

    # ChromaDB errors if n_results > collection.count()
    effective_k = min(top_k, total_count)

    # 1. Embed the candidate's resume with BAAI/bge-m3
    model = get_embedding_model()
    resume_embedding = model.encode(
        cleaned_resume,
        normalize_embeddings=True,
    ).tolist()

    # 2. Query ChromaDB collection
    try:
        query_results = collection.query(
            query_embeddings=[resume_embedding],
            n_results=effective_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.error("ChromaDB query failed: %s", exc)
        return []

    # 3. Format and convert results
    matched_jobs: list[dict[str, Any]] = []

    ids_list = query_results.get("ids", [[]])[0]
    metadatas_list = query_results.get("metadatas", [[]])[0]
    documents_list = query_results.get("documents", [[]])[0]
    distances_list = query_results.get("distances", [[]])[0]

    for idx in range(len(ids_list)):
        job_id = ids_list[idx]
        metadata = metadatas_list[idx] if idx < len(metadatas_list) else {}
        document = documents_list[idx] if idx < len(documents_list) else ""
        distance = distances_list[idx] if idx < len(distances_list) else 1.0

        # In cosine distance space: distance in [0, 2]
        # similarity = 1 - distance, clamped to [0.0, 1.0]
        similarity_score = round(max(0.0, min(1.0, 1.0 - float(distance))), 4)

        description_clean = metadata.get("description_clean") or document

        matched_jobs.append(
            {
                "id": str(job_id),
                "title": str(metadata.get("title", "بدون عنوان")),
                "company": str(metadata.get("company", "نامشخص")),
                "similarity_score": similarity_score,
                "source_url": str(metadata.get("source_url", "")),
                "description_clean": str(description_clean),
                "skills": str(metadata.get("skills", "")),
                "category": str(metadata.get("category", "")),
                "location": str(metadata.get("location", "")),
            }
        )

    # 4. Sort descending by similarity_score
    matched_jobs.sort(key=lambda x: x["similarity_score"], reverse=True)

    return matched_jobs
