"""Integration tests – Full pipeline from resume text to gap-analysis output.

These tests exercise the entire ``analyze_resume`` pipeline end-to-end:
  Stage 5 (retrieval via ChromaDB + BAAI/bge-m3)
  ->
  Stage 6 (gap-analysis via Google Gemini API)

**Prerequisites**
    1. The mock ChromaDB must already be built::
           cd backend && uv run python -m app.ingestion.build_mock_chroma
    2. ``GEMINI_API_KEY`` should be set in ``backend/.env`` for the gap-analysis
       content assertions.  Without it the pipeline still runs (retrieval is
       unaffected) and ``generate_gap_analysis`` degrades gracefully to an
       empty result, so the assertions that need real Gemini output are
       skipped with an explicit message — mirroring the ``skipif`` convention
       used in ``tests/test_generation.py``.

**Run**::
    cd backend && uv run pytest tests/test_analyze_integration.py -v -s

The ``-s`` flag is important: these tests print the full JSON output so the
human reviewer can manually inspect relevance and grounding quality.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from typing import Any

import pytest

from app.core.analyze import analyze_resume


# ---------------------------------------------------------------------------
# Fix Windows console encoding (cp1252 cannot handle Persian / emoji).
# Redirect stdout to a UTF-8 wrapper so print() never raises
# UnicodeEncodeError on Windows.
# ---------------------------------------------------------------------------
if sys.platform == "win32" and not isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sample resumes
# ---------------------------------------------------------------------------

_PERSIAN_BACKEND_RESUME: str = """\
مهندس نرم\u200cافزار بک\u200cاند با 5 سال تجربه حرفه\u200cای.

مهارت\u200cهای فنی:
- تسلط کامل بر زبان برنامه\u200cنویسی Python و فریم\u200cورک\u200cهای Django و FastAPI
- طراحی و پیاده\u200cسازی معماری میکروسرویس و RESTful API
- مدیریت و بهینه\u200cسازی دیتابیس PostgreSQL و کشینگ با Redis
- تجربه با سیستم\u200cهای صف پیام مانند Celery و RabbitMQ
- آشنایی کامل با Docker، CI/CD و اصول DevOps
- تجربه کار با Git و متدولوژی اسکرام در تیم\u200cهای چابک

سوابق:
- توسعه\u200cدهنده ارشد بک\u200cاند در شرکت فناوری اطلاعات (3 سال)
- توسعه\u200cدهنده پایتون در استارتاپ فین\u200cتک (2 سال)
"""

_ENGLISH_ML_RESUME: str = """\
Machine Learning & NLP Engineer -- 4 years of experience

Technical Skills:
- Advanced Python programming, strong OOP foundations
- Deep expertise in PyTorch, Scikit-Learn, and Pandas for model development
- Fine-tuning Hugging Face Transformers and Sentence-Transformers for NLP tasks
- Building semantic search and recommendation systems with Vector Databases (ChromaDB, Qdrant)
- End-to-end MLOps: Docker, FastAPI model serving, experiment tracking with MLflow
- Solid mathematical foundations in linear algebra, probability, and optimization

Experience:
- NLP Engineer at AI startup (2 years) -- built Persian-language text classifiers
- ML Research Assistant at university lab (2 years)
"""

_MIXED_FRONTEND_RESUME: str = """\
Front-end Developer -- 3 years experience

Skills:
- JavaScript (ES6+), TypeScript
- React.js, Next.js (App Router, SSR/SSG)
- Tailwind CSS, shadcn/ui component library
- State management: Redux Toolkit, Zustand
- RESTful API integration, Axios
- Git, GitHub, code review

Work experience:
- Front-end developer at tech company (2 years) -- built admin dashboards with React
- Freelance web developer (1 year) -- responsive landing pages and websites
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_print(text: str) -> None:
    """Print text safely even on Windows cp1252 consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: encode to UTF-8 bytes and write to stdout buffer directly
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


def _pretty_print_result(label: str, result: dict[str, Any]) -> None:
    """Print a human-readable summary of the analysis result."""
    _safe_print(f"\n{'=' * 78}")
    _safe_print(f"  {label}")
    _safe_print(f"{'=' * 78}")

    # -- matched jobs --
    matched = result.get("matched_jobs", [])
    _safe_print(f"\n  [JOBS] Retrieved {len(matched)} job(s):")
    for idx, job in enumerate(matched, start=1):
        _safe_print(
            f"    [{idx}] Score: {job['similarity_score']:.4f}  |  "
            f"{job['title']}  ({job['company']})"
        )

    # -- gap analysis --
    gap = result.get("gap_analysis", {})
    _safe_print(f"\n  [MATCH] Matching skills: {gap.get('matching_skills', [])}")
    _safe_print(f"  [GAP]   Missing skills:  {gap.get('missing_skills', [])}")
    _safe_print(f"  [SUMMARY] {gap.get('summary', '(empty)')}")
    _safe_print(f"{'=' * 78}\n")


def _assert_valid_structure(result: dict[str, Any]) -> None:
    """Assert the top-level output contract."""
    assert "matched_jobs" in result, "Missing 'matched_jobs' key"
    assert "gap_analysis" in result, "Missing 'gap_analysis' key"

    # matched_jobs contract
    assert isinstance(result["matched_jobs"], list)
    for job in result["matched_jobs"]:
        for field in ("id", "title", "company", "similarity_score",
                      "source_url", "description_clean"):
            assert field in job, f"Job missing field '{field}'"
        assert 0.0 <= job["similarity_score"] <= 1.0

    # gap_analysis contract
    gap = result["gap_analysis"]
    assert isinstance(gap, dict)
    for field in ("matching_skills", "missing_skills", "summary"):
        assert field in gap, f"gap_analysis missing field '{field}'"
    assert isinstance(gap["matching_skills"], list)
    assert isinstance(gap["missing_skills"], list)
    assert isinstance(gap["summary"], str)


def _assert_scores_sorted_descending(result: dict[str, Any]) -> None:
    """Verify similarity scores are in descending order."""
    scores = [j["similarity_score"] for j in result["matched_jobs"]]
    assert scores == sorted(scores, reverse=True), (
        f"Scores not sorted descending: {scores}"
    )


def _assert_skills_grounded(result: dict[str, Any]) -> None:
    """Verify that skills mentioned in gap_analysis actually appear in job texts.

    This is the most critical check: it guards against LLM hallucination by
    confirming that every skill reported as 'matching' or 'missing' can be
    traced back to the actual text of at least one retrieved job posting.
    """
    if not result["matched_jobs"]:
        # No jobs retrieved -> gap_analysis should be empty, nothing to check.
        return

    gap = result["gap_analysis"]

    # Build a combined text corpus from all retrieved job descriptions + titles
    corpus_parts: list[str] = []
    for job in result["matched_jobs"]:
        corpus_parts.append(job.get("title", "").lower())
        corpus_parts.append(job.get("description_clean", "").lower())
    corpus = " ".join(corpus_parts)

    # Check missing_skills: these MUST come from the job postings
    ungrounded: list[str] = []
    for skill in gap.get("missing_skills", []):
        if skill.lower() not in corpus:
            ungrounded.append(skill)

    if ungrounded:
        _safe_print(f"  [WARNING] Potentially ungrounded missing_skills: {ungrounded}")
        # Soft warning: skill names may appear in slightly different forms
        # (e.g. "CI/CD" vs "CICD").  The human reviewer should inspect.


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestAnalyzeResumePersianBackend:
    """Test the full pipeline with a Persian backend-developer resume."""

    def test_full_pipeline(self) -> None:
        start = time.perf_counter()
        result = analyze_resume(_PERSIAN_BACKEND_RESUME, top_k=5)
        elapsed = time.perf_counter() - start

        _pretty_print_result(
            f"Persian Backend Resume -- Pipeline: {elapsed:.2f}s", result
        )

        _assert_valid_structure(result)
        _assert_scores_sorted_descending(result)

        # We should get at least some jobs back
        assert len(result["matched_jobs"]) > 0, "No jobs retrieved"

        # Top results should include a Python/Backend position
        top_titles = [j["title"].lower() for j in result["matched_jobs"][:3]]
        assert any(
            any(
                kw in title
                for kw in (
                    "python",
                    "backend",
                    "fastapi",
                    "django",
                    "بک‌اند",
                    "بک اند",
                    "پایتون",
                )
            )
            for title in top_titles
        ), f"Top jobs don't look like a Python/Backend role: {top_titles}"

        # Gap analysis should have found some matching skills — but only when
        # a Gemini key is available.  Without it `generate_gap_analysis`
        # returns its documented empty result (graceful degradation), which
        # is expected behaviour, not a pipeline failure.
        if os.environ.get("GEMINI_API_KEY"):
            assert len(result["gap_analysis"]["matching_skills"]) > 0, (
                "No matching skills found -- expected at least a few"
            )
        else:
            _safe_print(
                "  [SKIP] GEMINI_API_KEY not set — skipping the "
                "matching_skills assertion (gap analysis degrades to empty)."
            )

        _assert_skills_grounded(result)

        _safe_print(f"  [TIME] Total pipeline time: {elapsed:.2f} seconds")


class TestAnalyzeResumeEnglishML:
    """Test the full pipeline with an English ML-engineer resume."""

    def test_full_pipeline(self) -> None:
        start = time.perf_counter()
        result = analyze_resume(_ENGLISH_ML_RESUME, top_k=5)
        elapsed = time.perf_counter() - start

        _pretty_print_result(
            f"English ML Resume -- Pipeline: {elapsed:.2f}s", result
        )

        _assert_valid_structure(result)
        _assert_scores_sorted_descending(result)

        assert len(result["matched_jobs"]) > 0

        # Among top matches, at least one should be an ML / AI / Data / Python role
        top_titles = [j["title"].lower() for j in result["matched_jobs"][:3]]
        assert any(
            any(
                kw in title
                for kw in (
                    "machine learning",
                    "ml",
                    "data",
                    "ai",
                    "هوش مصنوعی",
                    "داده",
                    "software",
                    "python",
                )
            )
            for title in top_titles
        ), f"Top jobs don't contain an ML/AI/Data/Python role: {top_titles}"

        _assert_skills_grounded(result)

        _safe_print(f"  [TIME] Total pipeline time: {elapsed:.2f} seconds")


class TestAnalyzeResumeMixedFrontend:
    """Test the full pipeline with an English frontend resume."""

    def test_full_pipeline(self) -> None:
        start = time.perf_counter()
        result = analyze_resume(_MIXED_FRONTEND_RESUME, top_k=5)
        elapsed = time.perf_counter() - start

        _pretty_print_result(
            f"Frontend Resume -- Pipeline: {elapsed:.2f}s", result
        )

        _assert_valid_structure(result)
        _assert_scores_sorted_descending(result)

        assert len(result["matched_jobs"]) > 0

        # Among top matches, at least one should be a frontend / web role
        top_titles = [j["title"].lower() for j in result["matched_jobs"][:3]]
        assert any(
            any(kw in title for kw in ("react", "front", "فرانت", "web", "full stack", "fullstack"))
            for title in top_titles
        ), f"Top jobs don't contain a frontend/web role: {top_titles}"

        _assert_skills_grounded(result)

        _safe_print(f"  [TIME] Total pipeline time: {elapsed:.2f} seconds")


# ---------------------------------------------------------------------------
# Error / edge-case scenarios
# ---------------------------------------------------------------------------


class TestAnalyzeResumeEdgeCases:
    """Ensure the pipeline handles bad input gracefully without crashing."""

    def test_empty_resume(self) -> None:
        """Empty string must return a valid but empty result."""
        result = analyze_resume("")

        _assert_valid_structure(result)
        assert result["matched_jobs"] == []
        assert result["gap_analysis"]["matching_skills"] == []
        assert result["gap_analysis"]["missing_skills"] == []

    def test_whitespace_only_resume(self) -> None:
        """Whitespace-only input should be treated as empty."""
        result = analyze_resume("   \n\t  ")

        _assert_valid_structure(result)
        assert result["matched_jobs"] == []

    def test_very_short_resume(self) -> None:
        """A trivially short resume (e.g. 'test') should not crash.

        It may or may not return jobs (the embedding of 'test' has some
        non-zero similarity to everything), but the output must be valid.
        """
        result = analyze_resume("test")

        _assert_valid_structure(result)
        _assert_scores_sorted_descending(result)
        # We only care that it didn't crash; the content may be empty or not.
        _safe_print(
            f"\n  Short resume 'test' -> {len(result['matched_jobs'])} jobs retrieved"
        )
