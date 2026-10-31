"""Typed application settings.

Values come from environment variables and/or a local `.env` file, so secrets (the
Google Gemini API key) and machine-specific paths (the ChromaDB directory) never end up
in version control. See `.env.example` for the supported keys.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Job Pulse backend."""

    model_config = SettingsConfigDict(
        # `env_file` paths are resolved relative to the process working directory, i.e.
        # `backend/` when the documented `uv run ...` commands are used.
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Unknown keys in `.env` are ignored, so later stages can add variables before
        # this class knows about them.
        extra="ignore",
    )

    # --- API metadata ---------------------------------------------------------------
    service_name: str = "jobpulse-backend"
    environment: str = "development"

    # --- CORS -----------------------------------------------------------------------
    # The Next.js frontend (Stage 8) runs on :3000 and calls this API from the browser.
    # List values must be provided as JSON in the environment, e.g.
    # CORS_ORIGINS=["http://localhost:3000","https://jobpulse.example"].
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Stage 6: Google Gemini API key -------------------------------------------
    # Read from GEMINI_API_KEY env var / .env.  Optional so the app can start
    # without it (generation calls will return empty results).
    gemini_api_key: str | None = None
    # --- Stage 4 & 5: Retrieval & Embeddings --------------------------------------
    # The same embedding model must be used for indexing and for querying.
    embedding_model_name: str = "BAAI/bge-m3"
    # Tokenizer truncation window applied on BOTH index and query sides so
    # vectors stay comparable. BGE-M3 hard limit is 8192 (Stage 3); 2048 is
    # the pragmatic CPU default (see ingestion/embed_and_index.py).
    embedding_max_seq_length: int = 2048
    chroma_persist_dir: str = "../data/chroma"
    chroma_collection_name: str = "job_postings"

    @property
    def resolved_chroma_dir(self) -> Path:
        """Return the absolute path to the ChromaDB directory.

        Handles both relative paths (resolved relative to the backend/ directory)
        and absolute paths, so scripts run from any working directory find the store.
        """
        path = Path(self.chroma_persist_dir)
        if path.is_absolute():
            return path
        # backend/app/core/config.py -> parents[2] is backend/
        backend_dir = Path(__file__).resolve().parents[2]
        return (backend_dir / path).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings, parsed once per process.

    Cached so it can be used as a FastAPI dependency without re-reading the environment
    on every request. Tests that need custom values can call ``get_settings.cache_clear()``.
    """
    return Settings()
