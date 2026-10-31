"""Health endpoint.

Used by the frontend, by `curl`, and by uptime checks. It must stay dependency-free
(no ChromaDB or Gemini imports) so that it keeps answering even when those subsystems
are unavailable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Returns 200 with basic service metadata while the API is responsive.",
)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Report that the API process is alive.

    Deliberately synchronous and side-effect free: no I/O happens here, so a 200 means
    "the web layer is up" rather than "every downstream dependency works".
    """
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=__version__,
        environment=settings.environment,
    )
