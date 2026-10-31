"""Cross-cutting infrastructure: configuration, logging, and shared clients.

For the end-to-end resume analysis pipeline, import :func:`analyze_resume`
from :mod:`app.core.analyze`.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.analyze import analyze_resume

__all__ = ["analyze_resume"]


def __getattr__(name: str):
    if name == "analyze_resume":
        from app.core.analyze import analyze_resume

        return analyze_resume
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

