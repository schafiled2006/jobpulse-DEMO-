"""FastAPI application entry point for the Job Pulse backend.

Run locally (from the `backend/` directory):

    uv run fastapi dev app/main.py     # auto-reload + Swagger UI on /docs
    # or
    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.api.routes.analyze import router as analyze_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage process-wide resources for the application's lifetime."""
    # --- startup ---
    yield
    # --- shutdown ---


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """Return a descriptive Persian JSON error response when rate limit is exceeded."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "تعداد درخواست‌های شما بیش از سقف مجاز (۵ درخواست در دقیقه) است. لطفاً چند لحظه بعد تلاش کنید."
        },
    )


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Uses the factory form so tests (and later CI) can build isolated instances via
    `create_app()` instead of importing a partially configured module-level app.
    """
    settings = get_settings()

    application = FastAPI(
        title="Job Pulse API",
        description=(
            "سامانه تطبیق رزومه و تحلیل شکاف مهارت با بازار کار ایران بر پایه معماری RAG "
            "(بازیابی با ChromaDB + BAAI/bge-m3 و تولید گزارش با Google Gemini)."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # Attach slowapi rate limiter state and error handler
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Configure CORS for Next.js frontend (Stage 8)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API feature routers
    application.include_router(health_router)
    application.include_router(analyze_router)

    return application


# Module-level instance referenced by `uvicorn app.main:app` / `fastapi dev app/main.py`.
app = create_app()
