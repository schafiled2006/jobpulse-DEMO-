"""Shared helpers for the Stage 1 spiders.

Kept dependency-free (stdlib only) so spiders stay light and the helpers are
trivially unit-testable without Scrapy installed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

# JobVision URLs look like https://jobvision.ir/jobs/<numeric-id>/<slug>.
JOB_ID_RE = re.compile(r"/jobs/(\d+)(?:/|$)")

# Best-effort language detection: count Arabic-script vs Latin letters.
_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 ``Z`` string (e.g. for scraped_at)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    """Unique id for one crawl run, e.g. ``2026-09-16T12-00-00_<8 hex>``."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def extract_job_id(url: str) -> str | None:
    """Pull the numeric JobVision id out of a posting URL, if present."""
    match = JOB_ID_RE.search(url or "")
    return match.group(1) if match else None


def md5_text(text: str) -> str:
    """Hex MD5 of UTF-8 text (used for the content_hash dedup key)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def detect_language(text: str) -> str:
    """Best-effort ``fa`` / ``en`` / ``mixed`` label for a raw description.

    Heuristic: if both scripts cover >20% of letters -> mixed, else the
    dominant script wins; empty/letterless text defaults to ``fa`` since the
    corpus is overwhelmingly Persian.
    """
    fa = len(_PERSIAN_RE.findall(text or ""))
    en = len(_LATIN_RE.findall(text or ""))
    total = fa + en
    if total == 0:
        return "fa"
    if fa / total > 0.8:
        return "fa"
    if en / total > 0.8:
        return "en"
    return "mixed"


# Maps JobVision English work-type tokens to the required schema vocabulary.
EMPLOYMENT_TYPE_MAP = {
    "full time": "full_time",
    "full-time": "full_time",
    "part time": "part_time",
    "part-time": "part_time",
    "remote": "remote",
    "contract": "contract",
    "internship": "internship",
}


def normalize_employment_type(value: str | None) -> str | None:
    """Map a raw work-type string onto the schema enum, else ``other``/None."""
    if not value:
        return None
    key = value.strip().lower()
    if key in EMPLOYMENT_TYPE_MAP:
        return EMPLOYMENT_TYPE_MAP[key]
    # Persian labels contain their Latin counterpart rarely; fall back to
    # keyword sniffing so we still emit something schema-valid.
    if "تمام" in value:
        return "full_time"
    if "پاره" in value:
        return "part_time"
    if "دورکار" in value or "remote" in key:
        return "remote"
    if "کارآموز" in value or "intern" in key:
        return "internship"
    if "پروژه" in value or "contract" in key:
        return "contract"
    return "other"
