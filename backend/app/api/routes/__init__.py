"""Feature routers.

One module per feature (`health.py`, `analyze.py`). Routers are
imported explicitly by `app.main` so the dependency direction stays obvious.
"""

from app.api.routes.analyze import router as analyze_router
from app.api.routes.health import router as health_router

__all__ = [
    "analyze_router",
    "health_router",
]
