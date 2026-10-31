"""Scrapy settings for the Job Pulse Stage 1 collector.

Politeness and safety values below are non-negotiable (see Stage 1 brief):
robots.txt is obeyed, autothrottle + download delay keep us gentle, retries
cover transient errors, and JOBDIR enables resume of the long Phase 2 crawl.
"""

from __future__ import annotations

# --- Identity -----------------------------------------------------------------
BOT_NAME = "jobpulse_scraper"
SPIDER_MODULES = ["jobpulse_scraper.spiders"]
NEWSPIDER_MODULE = "jobpulse_scraper.spiders"

# --- Politeness & safety (do not make more aggressive without review) ---------
ROBOTSTXT_OBEY = True
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 2
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504]

# Persist the scheduler + request queue on disk so a stopped Phase 2 crawl can
# be resumed with the same JOBDIR (see README.md).
JOBDIR = "crawls/jobvision_phase2"

# Be a good citizen and identify the crawl in server logs / contact.
USER_AGENT = "JobPulseResearchBot/0.1 (+https://github.com/AmiinMohammadi/JobPulse)"

# --- Output -------------------------------------------------------------------
# UTF-8 JSON Lines streamed to disk; items are never accumulated in memory.
FEED_EXPORT_ENCODING = "utf-8"

# --- Pipelines & middleware ----------------------------------------------------
ITEM_PIPELINES = {
    # Fills content_hash / scraped_at / first_seen / last_seen / scraper_run_id
    # and drops exact duplicates inside one run (Stage 2 re-checks globally).
    "jobpulse_scraper.pipelines.JobPulseMetaPipeline": 100,
}

DOWNLOADER_MIDDLEWARES = {
    # Warns/closes the spider when JobVision starts soft-banning us
    # (many tiny-but-200 responses in a row).
    "jobpulse_scraper.middlewares.SoftBanDetectionMiddleware": 543,
}

# Soft-ban detector tuning (see middlewares.py for semantics).
SOFTBAN_MIN_BODY_BYTES = 2000
SOFTBAN_WINDOW = 30
SOFTBAN_MAX_SHORT_RATIO = 0.8
SOFTBAN_CLOSE_SPIDER = True

# Quiet, parseable logs; keep a file per run for auditability.
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Stay on jobvision.ir during Phase 2; sitemap host is allowed for Phase 1.
ALLOWED_DOMAINS_NOTE = "enforced per-spider via allowed_domains"

# Cookies add fingerprint surface without helping static extraction.
COOKIES_ENABLED = False

# Retrying POSTs is off; our crawl is GET-only anyway.
RETRY_ENABLED = True
