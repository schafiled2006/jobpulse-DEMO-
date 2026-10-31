"""Job Pulse backend application package."""

# Single source of truth for the API version: it is exposed by `GET /health` and by the
# generated OpenAPI document. Keep it in sync with `version` in `pyproject.toml`.
__version__: str = "0.1.0"

__all__ = ["__version__"]
