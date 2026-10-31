"""Phase 2 - job-detail spider (slow, polite, resumable).

Reads the URL list produced by Phase 1 and scrapes one JobPostingItem
per posting. Extraction order per page:
1. <script id="ng-state"> (Angular transfer state, full Detail payload)
2. <script type="application/ld+json"> (schema.org JobPosting) - fallback
3. Plain HTML title/canonical - last resort for title/id only.

description_raw keeps the original HTML (Stage 2 cleans it). No
Playwright/JS rendering: the description is present in static HTML.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import scrapy
from scrapy.http import Request, Response

from jobpulse_scraper.items import JobPostingItem
from jobpulse_scraper.utils import (
    detect_language,
    extract_job_id,
    normalize_employment_type,
    utc_now_iso,
)

NG_STATE_SELECTOR = 'script#ng-state[type="application/json"]::text'
JSONLD_SELECTOR = 'script[type="application/ld+json"]::text'

# Never store personal contact info (Stage 1 brief).
PHONE_RE = re.compile(
    r"(\+?98[\s-]?9\d{2}[\s-]?\d{3}[\s-]?\d{4}|09\d{2}[\s-]?\d{3}[\s-]?\d{4})"
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class JobvisionDetailSpider(scrapy.Spider):
    """Scrape raw posting fields for every URL in the Phase 1 list."""

    name = "jobvision_detail"
    allowed_domains = ["jobvision.ir"]

    def __init__(
        self,
        input_file: str = "",
        limit: int = 0,
        fresh: str = "",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Point at Phase 1 output; limit caps pages, fresh wipes JOBDIR.

        Pass ``-a fresh=1`` for a clean run against a new input/output file:
        it deletes the persisted JOBDIR state (dupefilter + queue) at startup
        so previously fingerprinted URLs are crawled again. Omit it to resume
        an interrupted run with the identical command instead.
        """
        super().__init__(*args, **kwargs)
        if not input_file:
            raise ValueError(
                "Pass -a input_file=path to the Phase 1 URL list "
                "(jsonl with 'url' keys or plain .txt, one URL per line)."
            )
        self.input_file = input_file
        self.limit = int(limit or 0)
        self.fresh = str(fresh).lower() in ("1", "true", "yes")

    async def start(self) -> Any:
        """Stream URLs from disk without loading the whole list at once.

        Scrapy >= 2.13 calls ``start()``; the async form works there.
        NOTE on resume semantics (verified by test): with JOBDIR, re-running
        with the same ``-O`` file appends re-scraped items again (feed
        exporter does not dedupe), so a crash-resume can duplicate the tail
        of the output. In practice: resume with the same command, then let
        Stage 2 dedupe by ``content_hash`` (it always does). For exactness,
        re-crawl to a fresh ``-O`` file instead. For a new input/output
        file, pass ``-a fresh=1`` to wipe the stale dupefilter first —
        otherwise every URL is discarded as a duplicate (watch for
        ``dupefilter/filtered`` == queued count with zero responses).
        """
        if self.fresh:
            self._wipe_jobdir()
        count = 0
        for url in self._iter_urls(Path(self.input_file)):
            count += 1
            if self.limit and count > self.limit:
                break
            yield Request(
                url,
                callback=self.parse,
                errback=self._on_error,
                cb_kwargs={"source_url": url},
                dont_filter=False,
            )
        self.logger.info("Queued %d detail URLs from %s", count, self.input_file)

    @staticmethod
    def _iter_urls(path: Path) -> Iterable[str]:
        """Yield URLs from a Phase 1 .jsonl (or plain .txt) file."""
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("{"):
                    try:
                        url = str(json.loads(line).get("url") or "").strip()
                    except json.JSONDecodeError:
                        continue
                    if url:
                        yield url
                elif line.startswith("http"):
                    yield line

    def _on_error(self, failure: Any) -> None:
        """Log failed pages (non-200s after retries) without killing run."""
        self.logger.warning("Request failed: %s", failure)

    def _wipe_jobdir(self) -> None:
        """Delete persisted JOBDIR state for a clean run (``-a fresh=1``).

        Removes the dupefilter (``requests.seen``) and the disk queue so URLs
        fingerprinted by earlier runs are crawled again. Only the spider's own
        configured JOBDIR is touched; missing dirs are a no-op.
        """
        import shutil

        jobdir = str(getattr(self.settings, "get", lambda *a: None)("JOBDIR") or "")
        if not jobdir:
            self.logger.info("fresh=1: no JOBDIR configured, nothing to wipe")
            return
        path = Path(jobdir)
        if not path.is_absolute():
            # JOBDIR is relative to the Scrapy project root (where scrapy.cfg
            # lives); resolve against cwd, which is that dir per README usage.
            path = Path.cwd() / path
        if path.exists():
            shutil.rmtree(path)
            self.logger.info("fresh=1: wiped JOBDIR state at %s", path)
        else:
            self.logger.info("fresh=1: JOBDIR %s already empty", path)
    # -- parsing ----------------------------------------------------------
    def parse(self, response: Response, source_url: str) -> Iterable[JobPostingItem]:
        """Build one raw item; skip (warn) only when nothing usable remains."""
        ng_detail = self._extract_ng_detail(response)
        ld = self._extract_jsonld(response)

        title_raw = (
            self._str(ng_detail.get("title"))
            or self._str(ld.get("title"))
            or self._title_from_html(response)
        )
        # Raw description HTML: ng-state first, JSON-LD second. Stage 2
        # strips tags; here markup is kept verbatim as required.
        description_raw = (
            self._str(ng_detail.get("description"))
            or self._str(ld.get("description"))
            or ""
        )
        company = self._company(ng_detail, ld, response)
        location = self._location(ng_detail, ld)
        salary = self._salary(ng_detail, ld)
        employment_type = normalize_employment_type(
            self._work_type(ng_detail, ld) or self._html_employment_hint(response)
        )
        experience_level = self._seniority(ng_detail)
        category = self._category(ng_detail, ld)
        skills = self._skills(ng_detail)
        posted_date = self._posted_date(ng_detail, ld)
        job_id = extract_job_id(source_url) or self._str(
            ng_detail.get("id") or ld.get("identifier")
        )
        canonical = response.xpath('//link[@rel="canonical"]/@href').get()

        if not title_raw and not description_raw:
            self.logger.warning("Empty page, skipping: %s", source_url)
            return

        # Safety: never persist personal contact info even if embedded.
        description_raw = self._scrub_contacts(description_raw)

        now = utc_now_iso()
        yield JobPostingItem(
            id=str(job_id or canonical or response.url),
            source_url=source_url,
            scraped_at=now,
            posted_date=posted_date,
            status="active",
            title_raw=title_raw,
            description_raw=description_raw,
            language=detect_language(f"{title_raw}\n{description_raw}"),
            company=company,
            location=location,
            salary_range=salary,
            employment_type=employment_type,
            experience_level=experience_level,
            category=category,
            required_skills=skills,
            content_hash=None,  # pipeline computes MD5(title + description)
            first_seen=now,
            last_seen=now,
            scraper_run_id=None,  # pipeline stamps one id per run
        )

    # -- source 1: Angular ng-state ---------------------------------------
    def _extract_ng_detail(self, response: Response) -> dict[str, Any]:
        """Return the embedded JobPost/Detail payload, or {}."""
        raw = response.css(NG_STATE_SELECTOR).get()
        if not raw:
            return {}
        try:
            blob: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.debug("Unparseable ng-state on %s", response.url)
            return {}
        for key, val in blob.items():
            if "JobPost/Detail" in key and isinstance(val, dict):
                data = val.get("data", val)
                if isinstance(data, dict):
                    return data
        return {}

    # -- source 2: schema.org JSON-LD --------------------------------------
    def _extract_jsonld(self, response: Response) -> dict[str, Any]:
        """Return the first JobPosting JSON-LD block, or {}."""
        for raw in response.css(JSONLD_SELECTOR).getall():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            candidates = data if isinstance(data, list) else [data]
            for cand in candidates:
                if isinstance(cand, dict) and cand.get("@type") == "JobPosting":
                    return cand
        return {}
    # -- field builders (ng-state first, JSON-LD fallback) --
    @staticmethod
    def _str(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    def _title_from_html(self, response: Response) -> str | None:
        raw_title = response.xpath("//title/text()").get()
        if not raw_title:
            return None
        text = raw_title.strip().removeprefix("استخدام").strip()
        return text or raw_title.strip()

    def _company(
        self, ng: dict, ld: dict, response: Response
    ) -> str | None:
        comp = ng.get("company")
        if isinstance(comp, dict):
            name = comp.get("name")
            if isinstance(name, dict):
                return self._str(name.get("titleFa")) or self._str(name.get("titleEn"))
            return self._str(name)
        org = ld.get("hiringOrganization")
        if isinstance(org, dict):
            return self._str(org.get("name"))
        raw_title = response.xpath("//title/text()").get() or ""
        if " در " in raw_title:
            return raw_title.rsplit(" در ", 1)[-1].strip() or None
        return None

    def _location(self, ng: dict, ld: dict) -> str | None:
        loc = ng.get("location")
        if isinstance(loc, dict):
            parts: list[str] = []
            for section in ("region", "city", "province"):
                node = loc.get(section)
                if isinstance(node, dict):
                    label = self._str(node.get("titleFa")) or self._str(node.get("titleEn"))
                    if label:
                        parts.append(label)
            seen: list[str] = []
            for part in parts:
                if part not in seen:
                    seen.append(part)
            if seen:
                return ", ".join(seen)
        job_loc = ld.get("jobLocation")
        nodes = job_loc if isinstance(job_loc, list) else [job_loc]
        for node in nodes:
            if isinstance(node, dict):
                addr = node.get("address", node)
                if isinstance(addr, dict):
                    label = self._str(addr.get("addressLocality")) or self._str(addr.get("addressRegion"))
                    if label:
                        return label
        return None

    def _salary(self, ng: dict, ld: dict) -> str | None:
        salary = ng.get("salary")
        if isinstance(salary, dict):
            text = self._str(salary.get("titleFa")) or self._str(salary.get("title"))
            if text:
                return text
        elif isinstance(salary, (str, int, float)) and str(salary).strip():
            if str(salary).strip() != "12000":
                return str(salary).strip()
        base = ld.get("baseSalary")
        if isinstance(base, dict):
            return self._str(base.get("value"))
        if base not in (None, "", 12000, "12000"):
            return str(base)
        return None

    def _work_type(self, ng: dict, ld: dict) -> str | None:
        work = ng.get("workType")
        if isinstance(work, dict):
            return self._str(work.get("titleEn")) or self._str(work.get("titleFa"))
        emp = ld.get("employmentType")
        if isinstance(emp, list):
            emp = emp[0] if emp else None
        return self._str(emp)

    @staticmethod
    def _html_employment_hint(response: Response) -> str | None:
        text = " ".join(response.xpath("//body//text()").getall()[:200])
        for kw in ("تمام وقت", "پاره وقت", "دورکار", "full-time", "part-time"):
            if kw in text:
                return kw
        return None

    def _seniority(self, ng: dict) -> str | None:
        level = ng.get("seniorityLevel")
        if isinstance(level, dict):
            return self._str(level.get("titleFa")) or self._str(level.get("titleEn"))
        return None

    def _category(self, ng: dict, ld: dict) -> str | None:
        cats = ng.get("jobCategories")
        if isinstance(cats, list) and cats:
            first = cats[0]
            if isinstance(first, dict):
                return self._str(first.get("titleFa")) or self._str(first.get("titleEn"))
        return self._str(ld.get("occupationalCategory")) or self._str(ld.get("industry"))

    def _skills(self, ng: dict) -> list[str]:
        out: list[str] = []

        def push(label: object) -> None:
            text = self._str(label)
            if text and text not in out:
                out.append(text)
        for req in ng.get("softwareRequirements") or []:
            if isinstance(req, dict):
                soft = req.get("software")
                if isinstance(soft, dict):
                    push(soft.get("titleFa") or soft.get("titleEn"))
        for skill in ng.get("skills") or []:
            if isinstance(skill, dict):
                push(skill.get("titleFa") or skill.get("titleEn") or skill.get("title"))
            else:
                push(skill)
        for req in ng.get("languageRequirements") or []:
            if isinstance(req, dict):
                lang = req.get("language")
                if isinstance(lang, dict):
                    push(lang.get("titleFa") or lang.get("titleEn"))
        return out

    def _posted_date(self, ng: dict, ld: dict) -> str | None:
        act = ng.get("activationTime")
        if isinstance(act, dict) and act.get("date"):
            return str(act["date"])
        return self._str(ld.get("datePosted"))

    @staticmethod
    def _scrub_contacts(html_text: str) -> str:
        text = PHONE_RE.sub("[redacted-phone]", html_text or "")
        return EMAIL_RE.sub("[redacted-email]", text)
