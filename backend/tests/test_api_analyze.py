"""Integration and unit tests for the POST /analyze API endpoint (Stage 7).

Tests end-to-end HTTP request handling, file validation (PDF, DOCX), text input,
error handling (empty files, scanned PDFs, unsupported formats), rate limiting,
and response schema compliance without consuming Gemini API quota.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient
import pypdf
import pytest

from app.core.limiter import limiter
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Provide a clean TestClient instance for each test."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def disable_limiter_by_default():
    """Disable rate limiter for standard unit/validation tests to avoid 429 collisions."""
    limiter.enabled = False
    yield
    limiter.enabled = True


# ---------------------------------------------------------------------------
# Test helpers: In-memory file generators
# ---------------------------------------------------------------------------


def create_sample_docx(text: str) -> bytes:
    """Generate in-memory valid DOCX bytes containing the given text."""
    doc = Document()
    doc.add_heading("رزومه متقاضی", level=1)
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_sample_pdf(text: str) -> bytes:
    """Generate in-memory valid PDF bytes containing a real text stream."""
    stream_content = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET\n"
    raw_pdf = (
        f"%PDF-1.4\n"
        f"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        f"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        f"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        f"4 0 obj << /Length {len(stream_content)} >> stream\n"
        f"{stream_content}"
        f"endstream\nendobj\n"
        f"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        f"xref\n0 6\n"
        f"0000000000 65535 f \n"
        f"0000000010 00000 n \n"
        f"0000000060 00000 n \n"
        f"0000000117 00000 n \n"
        f"0000000220 00000 n \n"
        f"0000000320 00000 n \n"
        f"trailer << /Size 6 /Root 1 0 R >>\n"
        f"startxref\n400\n%%EOF"
    )
    return raw_pdf.encode("latin-1")


def create_blank_scanned_pdf() -> bytes:
    """Generate a valid PDF page with zero text (simulating a scanned document)."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# Standard mock result matching AnalyzeResponse contract
_MOCK_PIPELINE_RESULT: dict[str, Any] = {
    "matched_jobs": [
        {
            "id": "job-001",
            "title": "برنامه‌نویس ارشد پایتون (Senior Python Developer)",
            "company": "اسنپ (Snapp)",
            "similarity_score": 0.8542,
            "source_url": "https://jobvision.ir/jobs/snapp-senior-python-001",
            "description_clean": "توسعه‌دهنده ارشد پایتون در اسنپ. مسلط به Django و FastAPI.",
        }
    ],
    "gap_analysis": {
        "matching_skills": ["Python", "FastAPI", "PostgreSQL"],
        "missing_skills": ["Django", "Celery", "RabbitMQ"],
        "summary": "رزومه کاندیدا همخوانی مناسبی دارد اما نیازمند ارتقا در فریم‌ورک جنگو و ابزارهای صف است.",
    },
}


# ---------------------------------------------------------------------------
# Success scenarios
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointSuccess:
    """Verify successful submissions for raw text, DOCX, and PDF."""

    def test_analyze_with_raw_text(self, client: TestClient) -> None:
        """Raw text paste input returns 200 and matches the response schema."""
        sample_resume_text = (
            "مهندس نرم‌افزار با ۳ سال سابقه کار تخصصی با پایتون، فست‌پی‌آی و پایگاه داده پستگرس."
        )

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT) as mock_analyze:
            response = client.post(
                "/analyze",
                data={"text": sample_resume_text},
            )

            assert response.status_code == 200
            data = response.json()

            # Contract verification
            assert "matched_jobs" in data
            assert "gap_analysis" in data
            assert len(data["matched_jobs"]) == 1
            assert data["matched_jobs"][0]["id"] == "job-001"
            assert data["gap_analysis"]["matching_skills"] == ["Python", "FastAPI", "PostgreSQL"]

            mock_analyze.assert_called_once()
            called_text = mock_analyze.call_args.kwargs["resume_text"]
            assert sample_resume_text in called_text

    def test_analyze_with_docx_file(self, client: TestClient) -> None:
        """Valid DOCX file upload returns 200 and extracts text accurately."""
        sample_text = (
            "برنامه‌نویس فول‌استک با مهارت در React و Python و تجربه کار در محیط‌های چابک اسکرام."
        )
        docx_bytes = create_sample_docx(sample_text)

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT) as mock_analyze:
            response = client.post(
                "/analyze",
                files={
                    "file": (
                        "my_resume.docx",
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["matched_jobs"]) > 0

            # Verify the parser extracted our text and passed it to the pipeline
            mock_analyze.assert_called_once()
            passed_text = mock_analyze.call_args.kwargs["resume_text"]
            assert "برنامه‌نویس فول‌استک" in passed_text

    def test_analyze_with_pdf_file(self, client: TestClient) -> None:
        """Valid PDF file upload returns 200 and extracts selectable text."""
        sample_text = "Senior Python Engineer with 5 years experience in FastAPI and Django"
        pdf_bytes = create_sample_pdf(sample_text)

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT) as mock_analyze:
            response = client.post(
                "/analyze",
                files={
                    "file": (
                        "resume.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["matched_jobs"]) > 0

            mock_analyze.assert_called_once()
            passed_text = mock_analyze.call_args.kwargs["resume_text"]
            assert "Senior Python Engineer" in passed_text

    def test_top_k_defaults_to_five_and_passes_through(self, client: TestClient) -> None:
        """Default top_k=5 is forwarded to the pipeline when not specified."""
        sample_resume_text = "مهندس نرم‌افزار با ۳ سال سابقه کار تخصصی با پایتون، فست‌پی‌آی و پایگاه داده پستگرس."

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT) as mock_analyze:
            response = client.post("/analyze", data={"text": sample_resume_text})

            assert response.status_code == 200
            assert mock_analyze.call_args.kwargs["top_k"] == 5

    def test_top_k_query_param_is_forwarded(self, client: TestClient) -> None:
        """Explicit ?top_k=3 reaches analyze_resume unchanged."""
        sample_resume_text = "مهندس نرم‌افزار با ۳ سال سابقه کار تخصصی با پایتون، فست‌پی‌آی و پایگاه داده پستگرس."

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT) as mock_analyze:
            response = client.post("/analyze?top_k=3", data={"text": sample_resume_text})

            assert response.status_code == 200
            assert mock_analyze.call_args.kwargs["top_k"] == 3

    def test_top_k_out_of_range_rejected(self, client: TestClient) -> None:
        """top_k outside 1..10 is rejected by FastAPI validation (422)."""
        sample_resume_text = "مهندس نرم‌افزار با ۳ سال سابقه کار تخصصی با پایتون، فست‌پی‌آی و پایگاه داده پستگرس."

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT):
            assert client.post("/analyze?top_k=0", data={"text": sample_resume_text}).status_code == 422
            assert client.post("/analyze?top_k=11", data={"text": sample_resume_text}).status_code == 422


# ---------------------------------------------------------------------------
# Validation & Error handling scenarios
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointValidation:
    """Verify proper HTTP status codes and user-friendly error details on bad input."""

    def test_missing_both_file_and_text(self, client: TestClient) -> None:
        """Sending neither file nor text must return 400 Bad Request."""
        response = client.post("/analyze")
        assert response.status_code == 400
        assert "لطفاً یا فایل رزومه" in response.json()["detail"]

    def test_empty_raw_text(self, client: TestClient) -> None:
        """Sending whitespace-only text must return 400."""
        response = client.post("/analyze", data={"text": "     \n   "})
        assert response.status_code == 400
        assert "خالی است" in response.json()["detail"]

    def test_raw_text_too_short(self, client: TestClient) -> None:
        """Sending text shorter than MIN_EXTRACTED_TEXT_LENGTH must return 400."""
        response = client.post("/analyze", data={"text": "پایتون کار"})
        assert response.status_code == 400
        assert "بسیار کوتاه است" in response.json()["detail"]

    def test_empty_uploaded_file(self, client: TestClient) -> None:
        """Uploading a 0-byte file must return 400 Bad Request."""
        response = client.post(
            "/analyze",
            files={"file": ("empty_resume.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400
        assert "خالی است" in response.json()["detail"]

    def test_unsupported_file_extension(self, client: TestClient) -> None:
        """Uploading an unsupported file format (.txt or .png) must return 415."""
        response = client.post(
            "/analyze",
            files={"file": ("resume.txt", b"Some plain text here...", "text/plain")},
        )
        assert response.status_code == 415
        assert "پشتیبانی نمی‌شود" in response.json()["detail"]

    def test_scanned_pdf_error(self, client: TestClient) -> None:
        """A PDF with no selectable text (scanned) must return 400 explaining the issue."""
        scanned_bytes = create_blank_scanned_pdf()
        response = client.post(
            "/analyze",
            files={"file": ("scanned.pdf", scanned_bytes, "application/pdf")},
        )
        assert response.status_code == 400
        assert "اسکن‌شده" in response.json()["detail"]

    def test_corrupted_docx_file(self, client: TestClient) -> None:
        """A corrupted file with .docx extension must return 400."""
        corrupt_bytes = b"Not a real zip or docx content at all"
        response = client.post(
            "/analyze",
            files={
                "file": (
                    "broken.docx",
                    corrupt_bytes,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 400
        assert "خراب یا نامعتبر" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Rate limiting scenario
# ---------------------------------------------------------------------------


class TestAnalyzeEndpointRateLimiting:
    """Verify that slowapi correctly enforces 5 requests per minute."""

    def test_rate_limit_exceeded(self, client: TestClient) -> None:
        """A client sending more than 5 requests in a minute receives HTTP 429."""
        limiter.enabled = True
        sample_text = "مهندس نرم‌افزار پایتون با تخصص در جنگو و معماری مایکروسرویس و داکر."

        with patch("app.api.routes.analyze.analyze_resume", return_value=_MOCK_PIPELINE_RESULT):
            try:
                # 5 allowed requests
                for _ in range(5):
                    res = client.post("/analyze", data={"text": sample_text})
                    assert res.status_code == 200

                # 6th request must trigger 429
                res_blocked = client.post("/analyze", data={"text": sample_text})
                assert res_blocked.status_code == 429
                assert "سقف مجاز" in res_blocked.json()["detail"]
            finally:
                limiter.enabled = False
