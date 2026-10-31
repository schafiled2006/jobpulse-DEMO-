"""Job Pulse Stage 1 scraper package.

Two-phase design (see README.md):
  Phase 1 (discovery): sitemap -> data/urls_last_60_days.jsonl
  Phase 2 (detail):    URL list -> raw job postings JSONL
"""

from __future__ import annotations

__all__: list[str] = []
