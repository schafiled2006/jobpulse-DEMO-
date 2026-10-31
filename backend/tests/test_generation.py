"""Manual smoke-test for Stage 6 – generate_gap_analysis.

This test file contains hardcoded sample data (mixed Persian / English) so you
can verify the Gemini integration end-to-end without needing real scraped data.

How to run
~~~~~~~~~~
Make sure ``GEMINI_API_KEY`` is set in your environment (or in ``.env``), then::

    cd backend
    uv run pytest tests/test_generation.py -s

The ``-s`` flag disables output capture so you can see the full JSON result
printed to the console for manual inspection.

⚠️ This test makes **real** Gemini API calls – it will consume free-tier quota.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from app.retrieval.generation import generate_gap_analysis

# ---------------------------------------------------------------------------
# Hardcoded sample data (fictional, mixed Persian / English)
# ---------------------------------------------------------------------------

SAMPLE_RESUME: str = """\
نام: علی محمدی
ایمیل: ali.mohammadi@example.com

خلاصه:
توسعه‌دهنده بک‌اند با ۳ سال تجربه در Python و FastAPI.  آشنایی با PostgreSQL،
Docker و Git.  علاقه‌مند به یادگیری ماشین و پردازش زبان طبیعی.

مهارت‌ها:
- Python (Django, FastAPI, Flask)
- PostgreSQL, SQLite
- Docker, Docker Compose
- Git, GitHub
- REST API design
- Basic knowledge of machine learning (scikit-learn)

تجربه کاری:
- توسعه‌دهنده بک‌اند در شرکت فناوری نوین (۱۴۰۰–۱۴۰۲)
  طراحی و پیاده‌سازی APIهای RESTful با FastAPI و PostgreSQL.

تحصیلات:
- کارشناسی مهندسی کامپیوتر – دانشگاه تهران (۱۴۰۰)
"""

SAMPLE_JOBS: list[dict] = [
    {
        "id": "job-001",
        "title": "Senior Backend Developer",
        "company": "تپسی",
        "similarity_score": 0.87,
        "source_url": "https://jobvision.ir/jobs/1001",
        "description_clean": (
            "ما به یک توسعه‌دهنده ارشد بک‌اند نیاز داریم.\n"
            "مهارت‌های مورد نیاز:\n"
            "- تسلط بر Python و FastAPI یا Django\n"
            "- تجربه کار با PostgreSQL و Redis\n"
            "- آشنایی با Docker و Kubernetes\n"
            "- تجربه کار با سیستم‌های message queue مانند RabbitMQ یا Kafka\n"
            "- آشنایی با CI/CD pipelines\n"
            "- حداقل ۳ سال تجربه کاری مرتبط"
        ),
    },
    {
        "id": "job-002",
        "title": "Machine Learning Engineer",
        "company": "اسنپ",
        "similarity_score": 0.72,
        "source_url": "https://jobvision.ir/jobs/1002",
        "description_clean": (
            "به یک مهندس یادگیری ماشین با تجربه نیاز داریم.\n"
            "Requirements:\n"
            "- Strong Python programming skills\n"
            "- Experience with TensorFlow or PyTorch\n"
            "- Familiarity with NLP and transformer models\n"
            "- Experience with MLOps tools (MLflow, Kubeflow)\n"
            "- Knowledge of SQL and data pipelines\n"
            "- Good understanding of statistics and probability\n"
            "- آشنایی با Docker و Git الزامی است"
        ),
    },
    {
        "id": "job-003",
        "title": "Full-Stack Python Developer",
        "company": "دیجی‌کالا",
        "similarity_score": 0.81,
        "source_url": "https://jobvision.ir/jobs/1003",
        "description_clean": (
            "استخدام توسعه‌دهنده Full-Stack Python:\n"
            "- تسلط بر Python (FastAPI / Django)\n"
            "- آشنایی با React یا Vue.js برای فرانت‌اند\n"
            "- تجربه کار با PostgreSQL و MongoDB\n"
            "- آشنایی با Celery و Redis\n"
            "- تجربه با Elasticsearch یک مزیت است\n"
            "- تسلط بر Git و روش‌های Agile\n"
            "- مهارت‌های ارتباطی و کار تیمی"
        ),
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set — skipping live Gemini test.",
)
def test_generate_gap_analysis_structure_and_content() -> None:
    """Call generate_gap_analysis with sample data and validate the output schema.

    This test is intentionally verbose (prints full JSON) so you can visually
    inspect the quality of the analysis.
    """

    result = generate_gap_analysis(SAMPLE_RESUME, SAMPLE_JOBS)

    # --- Schema assertions -----------------------------------------------
    assert isinstance(result, dict), "Result must be a dict."
    assert "matching_skills" in result, "Missing key: matching_skills"
    assert "missing_skills" in result, "Missing key: missing_skills"
    assert "summary" in result, "Missing key: summary"

    assert isinstance(result["matching_skills"], list), "matching_skills must be a list."
    assert isinstance(result["missing_skills"], list), "missing_skills must be a list."
    assert isinstance(result["summary"], str), "summary must be a str."

    # --- Pretty-print for manual inspection ------------------------------
    # Write to a UTF-8 file so Persian text is always readable, even on
    # Windows consoles that default to cp1252.
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    output_path = Path(__file__).parent / "gap_analysis_output.json"
    output_path.write_text(output_json, encoding="utf-8")

    # Also print to console (use sys.stdout.buffer to avoid cp1252 crashes).
    header = "\n" + "=" * 72 + "\n  GAP ANALYSIS RESULT\n" + "=" * 72
    footer = "=" * 72
    full_output = f"{header}\n{output_json}\n{footer}\n"
    sys.stdout.buffer.write(full_output.encode("utf-8"))
    sys.stdout.buffer.flush()

    print(f"\n(Full output also saved to: {output_path})")

    # --- Basic sanity checks (non-empty) ---------------------------------
    assert len(result["matching_skills"]) > 0, (
        "Expected at least one matching skill for this sample data."
    )
    assert len(result["missing_skills"]) > 0, (
        "Expected at least one missing skill for this sample data."
    )
    assert len(result["summary"]) > 0, "Summary should not be empty."


def test_generate_gap_analysis_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """When GEMINI_API_KEY is not set, the function should return an empty result."""

    # Ensure the key is removed even if it exists in the real environment.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = generate_gap_analysis(SAMPLE_RESUME, SAMPLE_JOBS)

    assert result == {
        "matching_skills": [],
        "missing_skills": [],
        "summary": "",
    }


def test_generate_gap_analysis_empty_jobs() -> None:
    """When no jobs are provided, the function should still return a valid schema.

    Depending on the API key, this may call Gemini (with an empty job list) or
    return the empty fallback.
    """

    result = generate_gap_analysis(SAMPLE_RESUME, [])

    assert isinstance(result, dict)
    assert "matching_skills" in result
    assert "missing_skills" in result
    assert "summary" in result
