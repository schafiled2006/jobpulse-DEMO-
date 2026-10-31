"""Smoke tests for the Stage 0 API surface.

Run with (from the `backend/` directory):

    uv run pytest
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_health_returns_200_and_ok() -> None:
    """`GET /health` must answer 200 and report status 'ok'."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_response_contract() -> None:
    """The health payload is a contract used by the frontend and uptime checks.

    Field values are compared against `Settings` so a developer's local `.env` cannot
    break the suite, while the set of keys stays locked.
    """
    settings = get_settings()
    payload = client.get("/health").json()

    assert set(payload) == {"status", "service", "version", "environment"}
    assert payload["status"] == "ok"
    assert payload["service"] == settings.service_name
    assert payload["version"] == __version__


def test_openapi_document_exposes_health() -> None:
    """OpenAPI must keep describing the API, since it is the backend's public interface."""
    schema = client.get("/openapi.json").json()

    assert "/health" in schema["paths"]
    assert schema["info"]["title"] == "Job Pulse API"
