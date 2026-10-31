"""Stage 4 – Ingestion script to embed and index cleaned job postings into ChromaDB.

Reads cleaned records from `data/processed/jobvision_clean.jsonl`, computes dense
embeddings using `BAAI/bge-m3` via `sentence-transformers`, and persists them
along with structured metadata into the ChromaDB vector database.

Tokenizer window: BGE-M3 hard limit is 8192 tokens (Stage 3 decision: one ad =
one chunk, never split). Default ``--max-seq-length 2048`` covers the vast
majority of ads on CPU; use 8192 with a small batch size for a lossless rebuild.

Usage:
    # Index 200 records with tech-domain prioritization (recommended for fast dev testing):
    uv run python -m ingestion.embed_and_index --limit 200

    # Index all 1987 valid job postings from the Iranian market:
    uv run python -m ingestion.embed_and_index --all

    # Lossless rebuild with the full 8192-token window (needs more RAM, use small batches):
    uv run python -m ingestion.embed_and_index --all --max-seq-length 8192 --batch-size 8

    # Index in strict file order without tech prioritization:
    uv run python -m ingestion.embed_and_index --limit 200 --no-tech-priority
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Ensure backend root is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import chromadb
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("embed_and_index")

DEFAULT_CLEAN_PATH = _BACKEND_DIR.parent / "data" / "processed" / "jobvision_clean.jsonl"

TECH_KEYWORDS: set[str] = {
    "نرم",
    "وب",
    "برنامه",
    "داده",
    "هوش",
    "شبکه",
    "devops",
    "it",
    "frontend",
    "backend",
    "python",
    "react",
    "ai",
    "data",
    "machine learning",
    "مهندسی کامپیوتر",
    "sql",
    "سیستم",
}


def is_tech_job(item: dict[str, Any]) -> bool:
    """Check if a job posting belongs to IT, software, AI, or data disciplines."""
    category = (item.get("category") or "").lower()
    title = (item.get("title_clean") or item.get("title_raw") or "").lower()
    skills = [str(s).lower() for s in (item.get("required_skills") or [])]
    skills_str = " ".join(skills)

    for kw in TECH_KEYWORDS:
        if kw in category or kw in title or kw in skills_str:
            return True
    return False


def load_cleaned_records(
    file_path: Path,
    limit: int | None = None,
    prioritize_tech: bool = False,
) -> list[dict[str, Any]]:
    """Load valid records from the cleaned JSONL file.

    Parameters
    ----------
    file_path:
        Path to the `jobvision_clean.jsonl` file.
    limit:
        Maximum number of valid records to return. None loads all valid records.
    prioritize_tech:
        If True, groups tech, software, AI, and IT jobs first before filling
        the remaining limit with cross-domain jobs (Finance, Marketing, Sales, etc.).
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Cleaned data file not found at: {file_path}")

    valid_records: list[dict[str, Any]] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Line %d: Malformed JSON, skipping: %s", line_num, exc)
                continue

            # Only index valid items
            if not item.get("is_valid", True):
                continue

            valid_records.append(item)

    if prioritize_tech:
        tech_records: list[dict[str, Any]] = []
        other_records: list[dict[str, Any]] = []
        for rec in valid_records:
            if is_tech_job(rec):
                tech_records.append(rec)
            else:
                other_records.append(rec)

        ordered = tech_records + other_records
        logger.info(
            "Prioritized records: %d tech/IT jobs, %d cross-domain jobs (total: %d)",
            len(tech_records),
            len(other_records),
            len(ordered),
        )
    else:
        ordered = valid_records

    if limit is not None:
        ordered = ordered[:limit]

    logger.info("Selected %d records from %s for indexing", len(ordered), file_path)
    return ordered


def index_jobs(
    records: list[dict[str, Any]],
    batch_size: int = 32,
    clean_rebuild: bool = True,
    max_seq_length: int = 2048,
) -> int:
    """Embed and index job postings into ChromaDB.

    Parameters
    ----------
    records:
        List of cleaned job dictionaries to index.
    batch_size:
        Number of items embedded and upserted per batch.
    clean_rebuild:
        If True, drops the existing ChromaDB collection before indexing.
    max_seq_length:
        Maximum sequence length for the BGE-M3 tokenizer (default: 2048).
        Stage 3 locked the hard model limit at 8192 tokens (one ad = one
        chunk, never split). 2048 is the pragmatic CPU default: it covers
        the vast majority of ads (median embed_text ~681 chars) without the
        O(n^2) attention/RAM spike of a full 8192 context on CPU.  Pass
        8192 explicitly (CLI: ``--max-seq-length 8192`` with a small
        ``--batch-size``) for a lossless full rebuild when RAM allows.

    Returns
    -------
    int
        The total count of indexed items.
    """
    if not records:
        logger.warning("No records to index.")
        return 0

    settings = get_settings()
    chroma_dir = settings.resolved_chroma_dir
    collection_name = settings.chroma_collection_name
    model_name = settings.embedding_model_name

    logger.info("Connecting to ChromaDB at: %s", chroma_dir)
    client = chromadb.PersistentClient(path=str(chroma_dir))

    if clean_rebuild:
        try:
            client.delete_collection(name=collection_name)
            logger.info("Deleted existing collection '%s' for clean rebuild.", collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info("Loading embedding model '%s' ...", model_name)
    try:
        model = SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        model = SentenceTransformer(model_name)

    # Align query/index truncation window with the Stage 3 decision.
    # BGE-M3 hard limit is 8192; default 2048 avoids silent tail-truncation
    # of long ads that the old 512 window caused, without the RAM spike of
    # a full 8192 context on CPU.
    model.max_seq_length = max_seq_length
    logger.info("Embedding with max_seq_length=%d", model.max_seq_length)

    total_records = len(records)
    logger.info("Embedding and indexing %d jobs in batches of %d...", total_records, batch_size)

    start_time = time.perf_counter()

    for idx in range(0, total_records, batch_size):
        batch = records[idx : idx + batch_size]
        batch_ids: list[str] = []
        batch_documents: list[str] = []
        batch_texts_to_embed: list[str] = []
        batch_metadatas: list[dict[str, Any]] = []

        for job in batch:
            job_id = str(job["id"])
            title = str(job.get("title_clean") or job.get("title_raw") or "بدون عنوان")
            company = str(job.get("company") or "نامشخص")
            location = str(job.get("location") or "")
            category = str(job.get("category") or "")
            source_url = str(job.get("source_url") or "")
            description_clean = str(job.get("description_clean") or "")
            embed_text = str(job.get("embed_text") or f"{title}\n\n{description_clean}")

            # Extract structured skills
            raw_skills = job.get("required_skills") or []
            if isinstance(raw_skills, list):
                skills_str = ", ".join(str(s) for s in raw_skills if s)
            else:
                skills_str = str(raw_skills)

            employment_type = str(job.get("employment_type") or "")
            experience_level = str(job.get("experience_level") or "")

            batch_ids.append(job_id)
            batch_documents.append(description_clean)
            batch_texts_to_embed.append(embed_text)

            meta: dict[str, Any] = {
                "title": title[:500],
                "company": company[:500],
                "location": location[:500],
                "category": category[:500],
                "source_url": source_url[:500],
                "description_clean": description_clean[:3000],
                "skills": skills_str[:500],
                "employment_type": employment_type[:100],
                "experience_level": experience_level[:100],
            }
            batch_metadatas.append(meta)

        # Compute dense embeddings with BAAI/bge-m3 (already truncated to
        # model.max_seq_length set above).
        embeddings = model.encode(
            batch_texts_to_embed,
            batch_size=len(batch_texts_to_embed),
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        # add() fails on duplicate ids; upsert() handles both fresh
        # rebuilds and incremental re-runs (e.g. --no-clean-rebuild).
        try:
            collection.upsert(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch_documents,
                metadatas=batch_metadatas,
            )
        except Exception:
            # Older chromadb builds lack upsert(): fall back to add().
            collection.add(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch_documents,
                metadatas=batch_metadatas,
            )

        elapsed = time.perf_counter() - start_time
        processed = min(idx + batch_size, total_records)
        rate = processed / elapsed if elapsed > 0 else 0.0
        logger.info(
            "Progress: %d/%d (%.1f%%) in %.1f s (%.1f items/s)",
            processed,
            total_records,
            (processed / total_records) * 100,
            elapsed,
            rate,
        )

    total_time = time.perf_counter() - start_time
    logger.info(
        "Successfully indexed %d job postings into ChromaDB collection '%s' in %.1f seconds.",
        total_records,
        collection_name,
        total_time,
    )
    return total_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed and index cleaned JobVision jobs into ChromaDB.")
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of records to index (default: 200). Ignored if --all is set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Index all valid records in the file (1987 records).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding and DB storage (default: 32).",
    )
    parser.add_argument(
        "--no-tech-priority",
        action="store_true",
        help="Disable tech-domain prioritization when indexing with --limit.",
    )
    parser.add_argument(
        "--no-clean-rebuild",
        action="store_true",
        help="Do not delete existing collection before indexing (append/upsert).",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=2048,
        help=(
            "Tokenizer truncation window for BGE-M3 (default: 2048). "
            "Hard model limit is 8192; use 8192 with a small --batch-size "
            "for a lossless rebuild when RAM allows."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CLEAN_PATH,
        help="Path to cleaned JSONL file (default: data/processed/jobvision_clean.jsonl).",
    )
    args = parser.parse_args()

    limit = None if args.all else args.limit
    prioritize_tech = not args.no_tech_priority and limit is not None

    records = load_cleaned_records(
        args.input,
        limit=limit,
        prioritize_tech=prioritize_tech,
    )
    index_jobs(
        records,
        batch_size=args.batch_size,
        clean_rebuild=not args.no_clean_rebuild,
        max_seq_length=args.max_seq_length,
    )


if __name__ == "__main__":
    main()
