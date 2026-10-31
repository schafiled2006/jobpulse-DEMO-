"""Stage 9 CLI entry point (thin wrapper around ``eval.run_eval``).

Usage from ``backend/``::

    uv run python -m eval.cli --mode retrieval
    uv run python -m eval.cli --mode full --top-k 5
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.run_eval import main  # noqa: E402

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
