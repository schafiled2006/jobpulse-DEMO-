# Job Pulse — Stage 1 Scraper (Scrapy)

Collects **raw** JobVision postings. No cleaning here — Stage 2 (Hazm) does that.

## Layout

```text
backend/scraper/
├── scrapy.cfg                  # points Scrapy at jobpulse_scraper.settings
├── pyproject.toml              # scraper-only uv project (scrapy dependency)
├── jobpulse_scraper/
│   ├── settings.py             # politeness, JOBDIR, pipelines, soft-ban guard
│   ├── items.py                # JobPostingItem (exact Stage 1 schema) + UrlDiscoveryItem
│   ├── utils.py                # run ids, job-id parsing, language/employment-type helpers
│   ├── pipelines.py            # meta enrichment (hash/ids/dedup) + optional SQLite dedup
│   ├── middlewares.py          # SoftBanDetectionMiddleware
│   └── spiders/
│       ├── discovery.py        # Phase 1: sitemap -> URL list
│       └── detail.py           # Phase 2: URL list -> raw postings JSONL
└── README.md                   # this file
```

## Install

```bash
cd backend/scraper
uv sync --project .          # creates backend/scraper/.venv with scrapy
```

## Phase 1 — discovery (fast, ~1–2 min)

Parses `https://jobvision.ir/sitemap/jobposts.xml`, keeps entries with
`<lastmod>` in the last 60 days, streams them to JSONL:

```bash
cd backend/scraper
uv run --project . scrapy crawl jobvision_discovery \
  -O ../../data/urls_last_60_days.jsonl
# custom window, e.g. last 7 days:
uv run --project . scrapy crawl jobvision_discovery -a days=7 \
  -O ../../data/urls_last_7_days.jsonl
```

Phase 1 writes one row per fresh URL: `{"url": ..., "lastmod": ..., "job_id": ...}`.
Re-running with `-O` overwrites; use `-o` to append.

## Phase 2 — detail (slow, polite, resumable)

```bash
cd backend/scraper
# smoke test first (3 pages, fresh state):
uv run --project . scrapy crawl jobvision_detail \
  -a input_file=../../data/urls_last_60_days.jsonl -a limit=3 -a fresh=1 \
  -O /tmp/smoke.jsonl
# full run (streams to disk, never holds items in memory):
uv run --project . scrapy crawl jobvision_detail \
  -a input_file=../../data/urls_last_60_days.jsonl -a fresh=1 \
  -O ../../data/jobvision_raw.jsonl
```

**Fresh vs resume:** pass `-a fresh=1` when starting against a **new**
input/output file — it wipes the persisted JOBDIR state so previously
fingerprinted URLs are crawled again. Without it, a stale dupefilter discards
every URL as a duplicate (telltale: `dupefilter/filtered` == queued count with
zero responses) and the spider exits in seconds with 0 items.

**Resume:** the crawl state lives in `backend/scraper/crawls/jobvision_phase2`
(`JOBDIR`). If the run stops (Ctrl-C / crash / soft-ban close), re-run the
*same* command **without** `-a fresh=1` and with the *same* `-O` file, and
Scrapy continues with the remaining queue. Note (verified): the feed exporter
appends, so the resumed tail may duplicate a few items — harmless, because
Stage 2 dedupes by `content_hash` anyway. (`crawls/` and local `*.jsonl`
outputs are git-ignored.)

**Optional cross-run dedup** (skip already-seen hashes via SQLite):

```bash
uv run --project . scrapy crawl jobvision_detail \
  -a input_file=../../data/urls_last_60_days.jsonl \
  -O ../../data/jobvision_raw.jsonl \
  -s ITEM_PIPELINES='{"jobpulse_scraper.pipelines.JobPulseMetaPipeline": 100, "jobpulse_scraper.pipelines.SQLiteDedupPipeline": 200}'
```

## Politeness & safety

Locked in `settings.py`: `ROBOTSTXT_OBEY=True`, `DOWNLOAD_DELAY=2`,
`AUTOTHROTTLE` (3→30 s, 1.0 concurrency), 2 reqs/domain, 3 retries on
429/5xx. `SoftBanDetectionMiddleware` closes the spider if ≥80 % of the last
30 HTTP-200 bodies are suspiciously short (< 2000 bytes) — back off, then
resume via the same command.

## Expected runtime

- Phase 1: one XML fetch, ~1–2 min.
- Phase 2: ~2–4 s/page effective → ~55 k pages ≈ **40–60 h single-worker**.
  Run **off-peak (nights/weekends), spread over several days**; it is
  resumable, so Ctrl-C any time and continue later. For a quick Stage 2 sample,
  crawl with `-a limit=2000` (≈2 h) first.

## How extraction works (no JS rendering)

JobVision is an Angular SPA, but every posting page embeds its data in static
HTML — verified against live pages, so Playwright is unnecessary:

1. `<script id="ng-state" type="application/json">` carries the full
   `JobPost/Detail` API payload (title, raw description **HTML**, company,
   location, workType, seniority, salary, software/language requirements,
   categories, dates) — primary source.
2. `<script type="application/ld+json">` (schema.org `JobPosting`) — fallback.
3. `<title>` / canonical link — last resort for title/id.

`description_raw` keeps original HTML verbatim; phones/e-mails are redacted to
`[redacted-phone]` / `[redacted-email]`. Missing fields → `null` (`[]` for
`required_skills`). The pipeline fills `content_hash` (MD5 of title +
description), `scraped_at`/`first_seen`/`last_seen`, `scraper_run_id`, and
drops in-run duplicates.
