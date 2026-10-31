"""Downloader middleware: soft-ban detection.

JobVision (like many sites) may answer with HTTP 200 but a tiny/captcha body
when throttling a crawler. This middleware watches a sliding window of recent
responses: if too large a fraction are suspiciously short 200s, it logs a
loud warning and (by default) closes the spider so the operator can back off
and later resume via JOBDIR instead of hammering the site.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Response


class SoftBanDetectionMiddleware:
    """Warn/close on a run of suspiciously short HTTP-200 bodies."""

    def __init__(
        self,
        min_body_bytes: int,
        window: int,
        max_short_ratio: float,
        close_spider: bool,
    ) -> None:
        self.min_body_bytes = min_body_bytes
        self.window = window
        self.max_short_ratio = max_short_ratio
        self.close_spider = close_spider
        self.recent: Deque[bool] = deque(maxlen=window)
        self.crawler: Crawler | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> SoftBanDetectionMiddleware:
        """Read tuning knobs from settings (see settings.py)."""
        if not crawler.settings.getbool("SOFTBAN_ENABLED", True):
            raise NotConfigured("soft-ban detection disabled")
        mw = cls(
            min_body_bytes=crawler.settings.getint("SOFTBAN_MIN_BODY_BYTES", 2000),
            window=crawler.settings.getint("SOFTBAN_WINDOW", 30),
            max_short_ratio=crawler.settings.getfloat(
                "SOFTBAN_MAX_SHORT_RATIO", 0.8
            ),
            close_spider=crawler.settings.getbool("SOFTBAN_CLOSE_SPIDER", True),
        )
        mw.crawler = crawler
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        return mw

    def spider_opened(self, spider: Spider) -> None:
        """Reset the sliding window when a (re)run starts."""
        self.recent.clear()
        spider.logger.info(
            "Soft-ban guard on: window=%d min_bytes=%d max_short_ratio=%.2f",
            self.window,
            self.min_body_bytes,
            self.max_short_ratio,
        )

    def process_response(
        self, request: object, response: Response, spider: Spider
    ) -> Response:
        """Record each 200's size; trip when the window looks abusive."""
        if response.status == 200:
            is_short = len(response.body or b"") < self.min_body_bytes
            self.recent.append(is_short)
            if len(self.recent) >= self.window:
                ratio = sum(self.recent) / len(self.recent)
                if ratio >= self.max_short_ratio:
                    spider.logger.warning(
                        "Possible soft-ban: %.0f%% of last %d responses "
                        "were < %d bytes. Back off and resume later via JOBDIR.",
                        ratio * 100,
                        len(self.recent),
                        self.min_body_bytes,
                    )
                    self.recent.clear()  # avoid log spam on every response
                    if self.close_spider and self.crawler is not None:
                        self.crawler.engine.close_spider(
                            spider, reason="soft_ban_suspected"
                        )
        return response
