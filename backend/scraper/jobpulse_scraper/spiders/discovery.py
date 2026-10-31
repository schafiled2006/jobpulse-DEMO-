"""Phase 1 — sitemap discovery spider (fast & lightweight).

Reads https://jobvision.ir/sitemap/jobposts.xml, keeps entries whose
``<lastmod>`` is within the last N days (default 60), and yields one
``UrlDiscoveryItem`` per match. The URL list is streamed to disk via FEEDS
(e.g. ``data/urls_last_60_days.jsonl``); Phase 2 consumes that file.

Run (from ``backend/scraper/``):
    uv run --project . scrapy crawl jobvision_discovery \\
      -O ../../data/urls_last_60_days.jsonl
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import scrapy
from scrapy.http import Response

from jobpulse_scraper.items import UrlDiscoveryItem
from jobpulse_scraper.utils import extract_job_id

SITEMAP_URL = "https://jobvision.ir/sitemap/jobposts.xml"


class JobvisionDiscoverySpider(scrapy.Spider):
    """Yield fresh JobVision posting URLs found in the sitemap."""

    name = "jobvision_discovery"
    allowed_domains = ["jobvision.ir"]

    custom_settings: dict[str, Any] = {
        # Discovery is one big XML fetch: no throttle/cookies needed, and the
        # meta pipeline + soft-ban guard only make sense for Phase 2 pages.
        "ITEM_PIPELINES": {},
        "DOWNLOADER_MIDDLEWARES": {},
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 0,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "COOKIES_ENABLED": False,
        "JOBDIR": None,
    }

    def __init__(
        self,
        days: int = 60,
        sitemap_url: str = SITEMAP_URL,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Configure the age window (``-a days=30``) or a custom sitemap URL."""
        super().__init__(*args, **kwargs)
        self.days = int(days)
        self.sitemap_url = sitemap_url
        self.cutoff = datetime.now(timezone.utc) - timedelta(days=self.days)

    async def start(self) -> Any:
        """Fetch the single sitemap XML (parsed by hand in ``parse``).

        Scrapy >= 2.13 calls ``start()`` (not ``start_requests``); the async
        form below works on 2.13+ while staying import-compatible.
        """
        self.logger.info(
            "Fetching sitemap %s (lastmod >= %s)",
            self.sitemap_url,
            self.cutoff.date().isoformat(),
        )
        yield scrapy.Request(self.sitemap_url, callback=self.parse)


    def parse(self, response: Response) -> Iterable[UrlDiscoveryItem]:
        """Filter ``<url>`` entries by ``<lastmod>`` and yield fresh ones.

        Namespace-agnostic: the sitemap uses a default xmlns, so plain
        ``//url`` XPath would miss everything — ``local-name()`` sidesteps it.
        Malformed entries (no loc / bad date) are counted and skipped.
        """
        total = 0
        kept = 0
        skipped = 0
        for url_el in response.xpath("//*[local-name()='url']"):
            total += 1
            loc = (url_el.xpath("./*[local-name()='loc']/text()").get() or "").strip()
            lastmod_raw = (
                url_el.xpath("./*[local-name()='lastmod']/text()").get() or ""
            ).strip()
            if not loc:
                skipped += 1
                continue
            try:
                # Sitemap dates are ISO-8601 with 'Z'; fromisoformat needs +00:00.
                lastmod = datetime.fromisoformat(lastmod_raw.replace("Z", "+00:00"))
            except ValueError:
                self.logger.debug("Skipping entry with bad lastmod: %r", lastmod_raw)
                skipped += 1
                continue
            if lastmod < self.cutoff:
                continue
            kept += 1
            yield UrlDiscoveryItem(
                url=loc,
                lastmod=lastmod_raw,
                job_id=extract_job_id(loc),
            )
        self.logger.info(
            "Discovery done: %d sitemap entries, %d fresh (<= %d days), %d skipped",
            total,
            kept,
            self.days,
            skipped,
        )
