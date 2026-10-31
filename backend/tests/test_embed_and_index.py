"""Stage 4 tests – Embed and Index pipeline (fast, mocked dependencies).

Run from `backend/`::

    uv run pytest tests/test_embed_and_index.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ingestion.embed_and_index import (
    index_jobs,
    is_tech_job,
    load_cleaned_records,
)


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    """Create a temporary JSONL file with valid and invalid records."""
    file_path = tmp_path / "sample_clean.jsonl"
    records = [
        {
            "id": "job-1",
            "title_clean": "کارشناس حسابداری",
            "company": "شرکت بتا",
            "location": "اصفهان",
            "category": "مالی و حسابداری",
            "source_url": "https://jobvision.ir/jobs/1",
            "description_clean": "آشنایی کامل با نرم‌افزارهای سپیدار و اکسل پیشرفته",
            "embed_text": "کارشناس حسابداری | Sepidar, Excel | آشنایی کامل با نرم‌افزارها",
            "required_skills": ["Excel", "Sepidar"],
            "is_valid": True,
        },
        {
            "id": "job-2",
            "title_clean": "برنامه‌نویس پایتون",
            "title_raw": "برنامه نویس پایتون",
            "company": "شرکت آلفا",
            "location": "تهران",
            "category": "فناوری اطلاعات",
            "source_url": "https://jobvision.ir/jobs/2",
            "description_clean": "مسلط به فریمورک جنگو و مفاهیم وب با پایگاه داده پستگرس",
            "embed_text": "برنامه‌نویس پایتون | Python, Django | مسلط به فریمورک جنگو",
            "required_skills": ["Python", "Django", "PostgreSQL"],
            "is_valid": True,
        },
        {
            "id": "job-invalid",
            "title_clean": "کوتاه",
            "description_clean": "متن خیلی کوتاه",
            "embed_text": "کوتاه",
            "is_valid": False,  # Should be skipped
        },
    ]

    with open(file_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return file_path


def test_is_tech_job_detection() -> None:
    """Verify is_tech_job identifies IT/software keywords in title, category, or skills."""
    tech_item = {
        "title_clean": "برنامه‌نویس پایتون",
        "category": "مهندسی",
        "required_skills": ["Python"],
    }
    non_tech_item = {
        "title_clean": "کارشناس منابع انسانی",
        "category": "اداری و منابع انسانی",
        "required_skills": ["HR"],
    }
    assert is_tech_job(tech_item) is True
    assert is_tech_job(non_tech_item) is False


def test_load_cleaned_records_filters_invalid_and_applies_limit(sample_jsonl: Path) -> None:
    """Should only load valid records (is_valid=True) and respect limit parameter."""
    # Without limit: only 2 valid records
    all_valid = load_cleaned_records(sample_jsonl)
    assert len(all_valid) == 2
    assert all_valid[0]["id"] == "job-1"
    assert all_valid[1]["id"] == "job-2"

    # With limit=1
    limited = load_cleaned_records(sample_jsonl, limit=1)
    assert len(limited) == 1
    assert limited[0]["id"] == "job-1"


def test_load_cleaned_records_prioritize_tech(sample_jsonl: Path) -> None:
    """When prioritize_tech=True, tech jobs should appear first."""
    ordered = load_cleaned_records(sample_jsonl, prioritize_tech=True)
    assert len(ordered) == 2
    # job-2 is Python developer (tech), should come before job-1 (accounting)
    assert ordered[0]["id"] == "job-2"
    assert ordered[1]["id"] == "job-1"


def test_load_cleaned_records_missing_file(tmp_path: Path) -> None:
    """Should raise FileNotFoundError if the JSONL file does not exist."""
    missing = tmp_path / "non_existent.jsonl"
    with pytest.raises(FileNotFoundError):
        load_cleaned_records(missing)


def test_index_jobs_applies_max_seq_length() -> None:
    """index_jobs must forward max_seq_length to the embedding model."""
    records: list[dict[str, Any]] = [
        {
            "id": "job-0",
            "title_clean": "برنامه‌نویس پایتون",
            "company": "شرکت تست",
            "location": "تهران",
            "category": "IT",
            "source_url": "https://jobvision.ir/jobs/0",
            "description_clean": "شرح شغل آزمایشی",
            "embed_text": "متن امبدینگ شغل",
            "required_skills": ["Python"],
            "is_valid": True,
        }
    ]

    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    captured: dict[str, Any] = {}

    class _FakeModel:
        max_seq_length: int = 512

        def encode(self, texts: list[str], **kwargs: Any) -> Any:
            captured["max_seq_length"] = self.max_seq_length
            mock = MagicMock()
            mock.tolist = lambda: [[0.1] * 4 for _ in texts]
            return mock

    fake_model = _FakeModel()

    with (
        patch("ingestion.embed_and_index.chromadb.PersistentClient", return_value=mock_client),
        patch("ingestion.embed_and_index.SentenceTransformer", return_value=fake_model),
    ):
        index_jobs(records, batch_size=8, clean_rebuild=False, max_seq_length=2048)

    assert captured["max_seq_length"] == 2048


def test_index_jobs_upsert_fallback_to_add() -> None:
    """Hosts with old chromadb (no upsert) must still index via add()."""
    records: list[dict[str, Any]] = [
        {
            "id": "job-0",
            "title_clean": "برنامه‌نویس پایتون",
            "company": "شرکت تست",
            "location": "تهران",
            "category": "IT",
            "source_url": "https://jobvision.ir/jobs/0",
            "description_clean": "شرح شغل آزمایشی",
            "embed_text": "متن امبدینگ شغل",
            "required_skills": ["Python"],
            "is_valid": True,
        }
    ]

    mock_collection = MagicMock()
    mock_collection.upsert.side_effect = AttributeError("no upsert")
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    mock_model = MagicMock()
    mock_model.encode.side_effect = lambda texts, **kwargs: MagicMock(
        tolist=lambda: [[0.1] * 4 for _ in texts]
    )

    with (
        patch("ingestion.embed_and_index.chromadb.PersistentClient", return_value=mock_client),
        patch("ingestion.embed_and_index.SentenceTransformer", return_value=mock_model),
    ):
        assert index_jobs(records, batch_size=8, clean_rebuild=False) == 1

    mock_collection.add.assert_called_once()


def test_index_jobs_batches_and_stores_in_chromadb() -> None:
    """Verify batching, metadata mapping, skills serialization, and ChromaDB insertion."""
    records: list[dict[str, Any]] = [
        {
            "id": f"job-{i}",
            "title_clean": f"عنوان {i}",
            "company": "شرکت تست",
            "location": "تهران",
            "category": "IT",
            "source_url": f"https://jobvision.ir/jobs/{i}",
            "description_clean": f"شرح شغل آزمایشی شماره {i}",
            "embed_text": f"متن امبدینگ شغل شماره {i}",
            "required_skills": ["Python", "FastAPI"],
            "employment_type": "تمام وقت",
            "experience_level": "ارشد",
            "is_valid": True,
        }
        for i in range(5)
    ]

    mock_collection = MagicMock()
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    mock_model = MagicMock()
    # Mock return 1024-dim zero vectors
    mock_model.encode.side_effect = lambda texts, **kwargs: MagicMock(
        tolist=lambda: [[0.1] * 1024 for _ in texts]
    )

    with (
        patch("ingestion.embed_and_index.chromadb.PersistentClient", return_value=mock_client),
        patch("ingestion.embed_and_index.SentenceTransformer", return_value=mock_model),
    ):
        indexed_count = index_jobs(records, batch_size=2, clean_rebuild=True)

    assert indexed_count == 5
    # clean_rebuild should attempt to delete collection
    mock_client.delete_collection.assert_called_once()

    # With 5 items and batch_size=2: batches are 2, 2, 1 -> 3 upserts
    assert mock_collection.upsert.call_count == 3

    # Inspect first batch
    first_call_kwargs = mock_collection.upsert.call_args_list[0].kwargs
    assert first_call_kwargs["ids"] == ["job-0", "job-1"]
    assert len(first_call_kwargs["embeddings"]) == 2
    assert len(first_call_kwargs["metadatas"]) == 2
    assert first_call_kwargs["metadatas"][0]["title"] == "عنوان 0"
    assert first_call_kwargs["metadatas"][0]["company"] == "شرکت تست"
    assert first_call_kwargs["metadatas"][0]["skills"] == "Python, FastAPI"
    assert first_call_kwargs["metadatas"][0]["employment_type"] == "تمام وقت"
    assert first_call_kwargs["metadatas"][0]["experience_level"] == "ارشد"


def test_index_jobs_empty_list() -> None:
    """Calling index_jobs with an empty list should return 0 without error."""
    assert index_jobs([]) == 0
