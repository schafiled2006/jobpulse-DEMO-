"""Response models for the system (health) endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Payload returned by ``GET /health``.

    Kept intentionally small: it is used by the frontend and by uptime checks to confirm
    that the service is responsive and to see which version is running.
    """

    status: str = Field(
        default="ok",
        description="Always 'ok' when the service answers the request.",
    )
    service: str = Field(description="Service identifier, e.g. 'jobpulse-backend'.")
    version: str = Field(description="Backend version, taken from the app package.")
    environment: str = Field(description="Deployment environment, e.g. 'development'.")
