"""Stage 5 – Ingestion script to build a local mock ChromaDB collection.

Reads the mock job postings from `app.retrieval.mock_data`, computes dense
embeddings using `BAAI/bge-m3` via `sentence-transformers`, and stores them
into a persistent ChromaDB vector database.

Usage:
    # From the backend/ directory:
    uv run python -m app.ingestion.build_mock_chroma

    # Or from the project root:
    cd backend && uv run python -m app.ingestion.build_mock_chroma
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure backend root is on sys.path if executed directly as a script
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import chromadb
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.retrieval.mock_data import MOCK_JOBS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build_mock_chroma")


def build_mock_chromadb() -> int:
    """Embed mock job postings and store them in persistent ChromaDB.

    Returns
    -------
    int
        The number of job postings indexed.
    """
    settings = get_settings()
    chroma_dir = settings.resolved_chroma_dir
    model_name = settings.embedding_model_name
    collection_name = settings.chroma_collection_name

    logger.info("Initializing ChromaDB at: %s", chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))

    # Recreate or get collection with cosine similarity
    # Note: Using cosine distance space so distance = 1 - cosine_similarity
    try:
        # Delete if exists to ensure clean idempotent rebuild
        client.delete_collection(name=collection_name)
        logger.info("Deleted existing collection '%s' for clean rebuild.", collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info("Loading embedding model '%s' ...", model_name)
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        model = SentenceTransformer(model_name)

    logger.info("Embedding %d mock job postings...", len(MOCK_JOBS))

    # Prepare data for insertion
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    texts_to_embed: list[str] = []

    for job in MOCK_JOBS:
        job_id = job["id"]
        title = job["title"]
        company = job["company"]
        location = job.get("location", "")
        date_posted = job.get("date_posted", "")
        source_url = job.get("source_url", "")
        language = job.get("language", "")
        description_clean = job.get("description_clean", "")
        skills_extracted = job.get("skills_extracted", [])

        # The text to embed combines title and clean description for rich semantic representation
        text_for_embedding = f"{title}\n\n{description_clean}"

        ids.append(job_id)
        documents.append(description_clean)
        texts_to_embed.append(text_for_embedding)

        # ChromaDB metadata values must be primitive types (str, int, float, bool)
        metadatas.append(
            {
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "date_posted": date_posted,
                "source_url": source_url,
                "language": language,
                "description_clean": description_clean,
                "skills_extracted": ", ".join(skills_extracted),
            }
        )

    # Generate embeddings in batch
    embeddings = model.encode(
        texts_to_embed,
        batch_size=8,
        show_progress_bar=True,
        normalize_embeddings=True,
    ).tolist()

    # Add to ChromaDB collection
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    count = collection.count()
    logger.info("Successfully indexed %d job postings into collection '%s'.", count, collection_name)
    return count


if __name__ == "__main__":
    count = build_mock_chromadb()
    print(f"\nDone! Successfully indexed {count} jobs in ChromaDB.")
