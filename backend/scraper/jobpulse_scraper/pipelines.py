"""Pipelines: metadata enrichment + in-run dedup (Stage 1 only)."""

from __future__ import annotations

from typing import Any

from scrapy import Spider
from scrapy.exceptions import DropItem

from jobpulse_scraper.items import JobPostingItem
from jobpulse_scraper.utils import (
    detect_language,
    md5_text,
    new_run_id,
    utc_now_iso,
)


class JobPulseMetaPipeline:
    """Fill bookkeeping fields and drop exact duplicates within one run.

    - ``content_hash`` = MD5(title_raw + description_raw), computed here so
      spiders stay focused on extraction.
    - ``scraped_at`` / ``first_seen`` / ``last_seen`` default to now (UTC).
    - ``scraper_run_id`` is one id per process (created in ``open_spider``),
      so all items of a crawl share it as required by the schema.
    - ``status`` defaults to ``"active"``, ``language`` is best-effort
      detected when the spider left it blank, and ``required_skills``
      defaults to ``[]``.
    - An in-memory ``seen`` set drops re-crawled URLs/hashes *within* a run.
      Cross-run/global dedup is a Stage 2 job (SQLite/content_hash there).
    """

    def __init__(self) -> None:
        self.run_id: str = ""
        self.seen_hashes: set[str] = set()

    def open_spider(self, spider: Spider) -> None:
        """Create one run id per crawl (overridable via -s SCRAPER_RUN_ID=x)."""
        self.run_id = str(spider.settings.get("SCRAPER_RUN_ID") or new_run_id())
        self.seen_hashes = set()
        spider.logger.info("Scraper run id: %s", self.run_id)

    def process_item(self, item: JobPostingItem, spider: Spider) -> JobPostingItem:
        """Enrich bookkeeping fields; raise DropItem on exact duplicates."""
        title: str = str(item.get("title_raw") or "")
        desc: str = str(item.get("description_raw") or "")

        content_hash: str = str(
            item.get("content_hash") or md5_text(title + "\n" + desc)
        )
        if content_hash in self.seen_hashes:
            raise DropItem(f"duplicate content_hash in run: {content_hash}")
        self.seen_hashes.add(content_hash)

        now = utc_now_iso()
        item["content_hash"] = content_hash
        item["scraped_at"] = item.get("scraped_at") or now
        item["first_seen"] = item.get("first_seen") or item["scraped_at"]
        item["last_seen"] = item.get("last_seen") or item["scraped_at"]
        item["scraper_run_id"] = item.get("scraper_run_id") or self.run_id
        item["status"] = item.get("status") or "active"
        item["language"] = item.get("language") or detect_language(title + "\n" + desc)
        item["required_skills"] = item.get("required_skills") or []
        return item

    def close_spider(self, spider: Spider) -> None:
        """Log a one-line summary for the run audit trail."""
        spider.logger.info(
            "Run %s finished: %d unique items", self.run_id, len(self.seen_hashes)
        )


class SQLiteDedupPipeline:
    """Optional persistent dedup across runs (disabled by default).

    Enable with ``-s ITEM_PIPELINES`` override or by adding to settings once
    tested. Stores ``content_hash -> source_url`` in a tiny SQLite file so
    re-crawls skip already-seen postings instead of re-emitting them.

    For the MVP this is intentionally simple: no migrations, one table.
    """

    def __init__(self, path: str = "crawls/dedup.sqlite3") -> None:
        self.path = path
        self._conn: Any = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> SQLiteDedupPipeline:
        """Build from Scrapy settings (``SQLITE_DEDUP_PATH`` overridable)."""
        path = str(crawler.settings.get("SQLITE_DEDUP_PATH", "crawls/dedup.sqlite3"))
        return cls(path)

    def open_spider(self, spider: Spider) -> None:
        """Open (and create) the SQLite dedup database."""
        import os
        import sqlite3

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen"
            " (content_hash TEXT PRIMARY KEY, source_url TEXT, seen_at TEXT)"
        )
        self._conn.commit()

    def process_item(self, item: JobPostingItem, spider: Spider) -> JobPostingItem:
        """Drop items whose content_hash was seen in any previous run."""
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT 1 FROM seen WHERE content_hash = ?",
            (str(item.get("content_hash")),),
        )
        if cur.fetchone():
            raise DropItem(f"already seen in previous run: {item.get('source_url')}")
        self._conn.execute(
            "INSERT INTO seen (content_hash, source_url, seen_at) VALUES (?, ?, ?)",
            (
                str(item.get("content_hash")),
                str(item.get("source_url")),
                str(item.get("scraped_at")),
            ),
        )
        self._conn.commit()
        return item

    def close_spider(self, spider: Spider) -> None:
        """Close the SQLite handle."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
