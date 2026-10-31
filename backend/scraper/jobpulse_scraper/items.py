"""Raw job-posting item — exact Stage 1 schema.

Every field below mirrors the contract in the Stage 1 brief. Missing values
are stored as ``None`` (or ``[]`` for ``required_skills``). Cleaning and
normalization are Stage 2 concerns; here we persist raw text only.
"""

from __future__ import annotations

import scrapy


class JobPostingItem(scrapy.Item):
    """One raw JobVision posting, exactly as scraped."""

    id = scrapy.Field()  # site listing id, else canonical URL
    source_url = scrapy.Field()  # full URL of the posting page
    scraped_at = scrapy.Field()  # ISO-8601 UTC timestamp (pipeline-filled)
    posted_date = scrapy.Field()  # live-date if shown, else None
    status = scrapy.Field()  # always "active" on first scrape
    title_raw = scrapy.Field()  # unmodified title
    description_raw = scrapy.Field()  # raw description HTML (NOT cleaned)
    language = scrapy.Field()  # "fa" | "en" | "mixed" (best effort)
    company = scrapy.Field()  # company name or None
    location = scrapy.Field()  # city/region text or None
    salary_range = scrapy.Field()  # raw salary text or None
    employment_type = scrapy.Field()  # normalized token or None (see spider)
    experience_level = scrapy.Field()  # raw seniority text or None
    category = scrapy.Field()  # category text or None
    required_skills = scrapy.Field()  # structured skill tags, else []
    content_hash = scrapy.Field()  # MD5(title_raw + description_raw)
    first_seen = scrapy.Field()  # == scraped_at on first run
    last_seen = scrapy.Field()  # == scraped_at on first run
    scraper_run_id = scrapy.Field()  # UUID/timestamp identifying this crawl


class UrlDiscoveryItem(scrapy.Item):
    """One Phase 1 discovery row: a sitemap URL that passed the age filter."""

    url = scrapy.Field()
    lastmod = scrapy.Field()
    job_id = scrapy.Field()
