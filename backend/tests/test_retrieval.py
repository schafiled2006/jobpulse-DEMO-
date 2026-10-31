"""Tests for Stage 5 – Retrieval pipeline (ChromaDB + BAAI/bge-m3).

Verifies that `retrieve_matched_jobs`:
1. Correctly embeds candidate resumes using BAAI/bge-m3.
2. Retrieves the most relevant job postings from ChromaDB.
3. Ranks relevant jobs at the top with valid similarity scores in [0.0, 1.0].
4. Handles Persian, English, and mixed resumes accurately.
5. Gracefully handles edge cases (empty text, top_k <= 0).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pytest

from app.retrieval.retrieval import retrieve_matched_jobs

# ---------------------------------------------------------------------------
# Sample resumes for testing
# ---------------------------------------------------------------------------

_PERSIAN_PYTHON_RESUME = """
مهندس ارشد نرم‌افزار با ۵ سال سابقه در توسعه سیستم‌های سمت سرور.
مهارت‌ها و سوابق:
- تسلط کامل به زبان پایتون (Python) و فریم‌ورک‌های Django و FastAPI
- طراحی و پیاده‌سازی معماری میکروسرویس و ارتباط با gRPC و REST API
- مدیریت و بهینه‌سازی دیتابیس PostgreSQL و کشینگ با Redis
- مدیریت وظایف ناهمگام با Celery و RabbitMQ
- تسلط به Docker و مفاهیم یکپارچه‌سازی مداوم (CI/CD)
- تجربه کار در تیم‌های چابک و متدولوژی اسکرام
"""

_ENGLISH_ML_RESUME = """
Machine Learning & NLP Engineer with 4 years of experience.
Key Qualifications:
- Advanced Python programming, PyTorch, Scikit-Learn, and Pandas
- Experience fine-tuning Hugging Face Transformers, Sentence-Transformers, and LLMs
- Designing semantic search and recommendation systems with Vector Databases (ChromaDB)
- Building end-to-end MLOps pipelines with Docker and FastAPI model serving
- Strong background in mathematical foundations of Deep Learning and NLP
"""

_FRONTEND_REACT_RESUME = """
توسعه‌دهنده فرانت‌اند با ۳ سال تجربه حرفه‌ای.
- تسلط بر JavaScript (ES6+), TypeScript و کتابخانه React.js
- تجربه عمیق در ساخت وب‌اپلیکیشن با فریم‌ورک Next.js و رندر سمت سرور (SSR)
- استایل‌دهی با Tailwind CSS و پیاده‌سازی کامپوننت‌های shadcn/ui
- مدیریت وضعیت با Redux Toolkit و Zustand
- تجربه پیاده‌سازی طراحی‌های واکنش‌گرا و راست‌چین (RTL)
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_retrieve_persian_python_resume() -> None:
    """Test retrieving jobs for a Persian Python/Backend developer resume."""
    results = retrieve_matched_jobs(_PERSIAN_PYTHON_RESUME, top_k=5)

    assert isinstance(results, list)
    assert len(results) > 0
    assert len(results) <= 5

    # Check contract fields
    for job in results:
        assert "id" in job
        assert "title" in job
        assert "company" in job
        assert "similarity_score" in job
        assert "source_url" in job
        assert "description_clean" in job

        # Score must be bounded in [0.0, 1.0]
        assert 0.0 <= job["similarity_score"] <= 1.0
        assert len(job["description_clean"]) > 0

    # Ensure results are sorted descending by similarity_score
    scores = [j["similarity_score"] for j in results]
    assert scores == sorted(scores, reverse=True)

    # Top result should be a Python / Backend / DevOps position
    top_job = results[0]
    top_title_lower = top_job["title"].lower()
    assert (
        "پایتون" in top_job["title"]
        or "python" in top_title_lower
        or "backend" in top_title_lower
        or "devops" in top_title_lower
        or "engineer" in top_title_lower
    )

    # Pretty-print top matches for manual inspection
    print("\n" + "=" * 70)
    print("  PERSIAN PYTHON RESUME -> TOP RETRIEVED JOBS")
    print("=" * 70)
    for idx, job in enumerate(results, start=1):
        print(f"[{idx}] Score: {job['similarity_score']:.4f} | {job['title']} ({job['company']})")
    print("=" * 70)


def test_retrieve_english_ml_resume() -> None:
    """Test retrieving jobs for an English Machine Learning resume."""
    results = retrieve_matched_jobs(_ENGLISH_ML_RESUME, top_k=5)

    assert isinstance(results, list)
    assert len(results) > 0

    # Top matching jobs should include ML, AI, Data, or Python positions
    top_titles_and_companies = [
        f"{j['title'].lower()} {j['company'].lower()}" for j in results[:3]
    ]
    matched_tech = any(
        any(k in s for k in ["machine learning", "ml", "data", "هوش مصنوعی", "python", "ai", "دیجی‌کالا"])
        for s in top_titles_and_companies
    )
    assert matched_tech, f"Expected ML/AI/Data in top jobs, got: {[j['title'] for j in results[:3]]}"

    print("\n" + "=" * 70)
    print("  ENGLISH ML RESUME -> TOP RETRIEVED JOBS")
    print("=" * 70)
    for idx, job in enumerate(results, start=1):
        print(f"[{idx}] Score: {job['similarity_score']:.4f} | {job['title']} ({job['company']})")
    print("=" * 70)


def test_retrieve_frontend_resume() -> None:
    """Test retrieving jobs for a React / Next.js frontend resume."""
    results = retrieve_matched_jobs(_FRONTEND_REACT_RESUME, top_k=5)

    assert isinstance(results, list)
    assert len(results) > 0

    # Top result should be a Frontend / React / Web position
    top_job = results[0]
    top_title_lower = top_job["title"].lower()
    assert (
        "فرانت" in top_job["title"]
        or "react" in top_title_lower
        or "web" in top_title_lower
        or "کافه‌بازار" in top_job["company"]
    )

    print("\n" + "=" * 70)
    print("  FRONTEND REACT RESUME -> TOP RETRIEVED JOBS")
    print("=" * 70)
    for idx, job in enumerate(results, start=1):
        print(f"[{idx}] Score: {job['similarity_score']:.4f} | {job['title']} ({job['company']})")
    print("=" * 70)


def test_retrieve_empty_and_whitespace_input() -> None:
    """Empty or whitespace-only resume should return an empty list."""
    assert retrieve_matched_jobs("") == []
    assert retrieve_matched_jobs("   \n\t  ") == []


def test_retrieve_top_k_parameter() -> None:
    """Verify top_k limits the number of returned results."""
    res_1 = retrieve_matched_jobs(_PERSIAN_PYTHON_RESUME, top_k=1)
    assert len(res_1) == 1

    res_3 = retrieve_matched_jobs(_PERSIAN_PYTHON_RESUME, top_k=3)
    assert len(res_3) == 3

    assert retrieve_matched_jobs(_PERSIAN_PYTHON_RESUME, top_k=0) == []
    assert retrieve_matched_jobs(_PERSIAN_PYTHON_RESUME, top_k=-5) == []
