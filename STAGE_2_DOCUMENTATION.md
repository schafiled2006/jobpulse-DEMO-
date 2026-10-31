# Stage 2 — Clean & Normalize

> Audience: JobPulse collaborators (owner + reviewer).
> Scope: `data/raw/jobvision_raw.jsonl` to `data/processed/*`.
> Stack: `beautifulsoup4` + `hazm` (locked), `uv`, Python 3.11.

## 1. Stage Overview

Goal: turn raw Stage 1 HTML postings into clean, consistent text ready for
embedding, while keeping the originals for traceability.

Why it matters for RAG: the Stage 4 embedding model compares resume text
against `embed_text`. HTML tags, entities, mixed Arabic/Persian characters,
extra spaces, and duplicates all degrade vector quality. Stage 2 removes that
noise once, offline, so retrieval (Stage 5) and generation (Stage 6) work on
grounded, comparable text.

## 2. What Was Implemented



### Files created / modified


| Path                                   | Status   | Purpose                                        |
| -------------------------------------- | -------- | ---------------------------------------------- |
| `backend/ingestion/__init__.py`        | new      | Package marker for the offline pipeline        |
| `backend/ingestion/cleaner.py`         | new      | Full pipeline plus CLI (`clean_file` / `main`) |
| `backend/tests/test_cleaner.py`        | new      | 4 spec tests, no network, no files             |
| `backend/pyproject.toml` (+ `uv.lock`) | modified | Added `beautifulsoup4>=4.12`, `hazm>=0.10`     |




### Main functions (`backend/ingestion/cleaner.py`)


| Function                            | Responsibility                                            |
| ----------------------------------- | --------------------------------------------------------- |
| `strip_html`                        | BeautifulSoup `get_text(separator=" ")`; decodes entities |
| `collapse_whitespace`               | Collapse `[ \t]+`, strip; preserves newlines and ZWNJ     |
| `normalize_skills`                  | Strip-only skill list; never Hazm (keeps `Html & CSS`)    |
| `build_embed_text`                  | `title | skills | desc`, or `title | desc` without skills |
| `fix_posted_date`                   | Append `Z` when missing; `None` stays `None`              |
| `clean_record`                      | Ordered per-record pipeline (see below)                   |
| `deduplicate_by_hash`               | Drop later `content_hash` duplicates, keep first          |
| `build_report` / `write_sample_csv` | Stats string plus 20-row stratified CSV                   |
| `clean_file` / `main`               | Read JSONL, write 3 outputs, print report                 |




### Exact pipeline (per record, in order)

1. Copy all original fields into the output dict.
2. Fix `posted_date`: append `Z` if a non-empty string lacks it.
3. Strip HTML with `BeautifulSoup(description_raw, "html.parser").get_text(separator=" ")`.
4. Collapse `[ \t]+` to a single space, strip.
5. Hazm-normalize description to `description_clean` and `title_raw` to `title_clean` (one `Normalizer()` built once outside the loop).
6. Collapse whitespace again after Hazm.
7. Normalize skills: keep stripped non-empty strings only.
8. Build `embed_text` (see table above).
9. Set `description_clean_length` and `is_valid` (`length >= 20`).
10. Add `cleaned_at` (UTC ISO-8601 ending in `Z`).
11. Deduplicate by `content_hash` (keep first, log dropped ids).



## 3. Input and Output



### Input

- Path: `data/raw/jobvision_raw.jsonl` (UTF-8 JSONL, one object per line).
- Size at implementation time: **1989 records** in the Stage 1
`JobPostingItem` schema (`id`, `source_url`, `title_raw`,
`description_raw` HTML, `language`, `company`, `location`, `salary_range`,
`employment_type`, `experience_level`, `category`, `required_skills`,
`content_hash`, `posted_date`, `scraped_at`, `first_seen`, `last_seen`,
`scraper_run_id`, `status`).



### Outputs (all in `data/processed/`, git-ignored, UTF-8)


| File                         | Contents                                                        |
| ---------------------------- | --------------------------------------------------------------- |
| `jobvision_clean.jsonl`      | Primary output: one cleaned record per line, Persian kept as-is |
| `jobvision_clean_sample.csv` | 20 stratified rows (by `language`, `seed=42`) for human review  |
| `cleaning_report.txt`        | Same report printed to stdout: counts, languages, length stats  |




### New fields on every cleaned record


| Field                      | Type | Rule                                                                |
| -------------------------- | ---- | ------------------------------------------------------------------- |
| `title_clean`              | str  | Hazm-normalized plus collapsed `title_raw`                          |
| `description_clean`        | str  | HTML-stripped plus Hazm-normalized plus collapsed `description_raw` |
| `description_clean_length` | int  | `len(description_clean)`                                            |
| `embed_text`               | str  | Stage 4 input (`title | skills | desc`)                             |
| `is_valid`                 | bool | `description_clean_length >= 20`                                    |
| `cleaned_at`               | str  | UTC ISO-8601 ending in `Z`                                          |


Untouched: `description_raw`, `title_raw`, `content_hash` (never recomputed).
Never Hazm-ed: `required_skills`, `company`, `location`, `category`,
`salary_range`.

## 4. How to Run

```bash
cd backend
uv sync                            # install beautifulsoup4 + hazm
uv run python -m ingestion.cleaner # or: uv run python ingestion/cleaner.py
uv run pytest tests/test_cleaner.py -v
uv run pytest -q                   # full suite; live Gemini test skips without key
```



## 5. Success Criteria and Validation

Actual run (1989 records, about 4 s):

```text
Input records (raw JSONL):        1989
After dedup (kept):               1989
Dropped duplicates (hash):        0
is_valid=True  (>= 20 chars): 1987
is_valid=False (< 20 chars):  2
Language distribution: fa: 1152, mixed: 810, en: 27
description_clean_length: min=13 max=6992 mean=795.3
embed_text length:        min=29 max=7019 mean=843.6
```

What "clean" means: no `div`/`p`/`li` tags left (verified 0 hits), entities
decoded, whitespace collapsed, ZWNJ preserved (1851 records contain it),
skills literal, hashes identical to raw.

Spot-check in 3 to 5 minutes:

```bash
cat data/processed/cleaning_report.txt
# open data/processed/jobvision_clean_sample.csv in a spreadsheet (20 rows)
python3 -c "import json; r=json.loads(open('data/processed/jobvision_clean.jsonl',encoding='utf-8').readline()); print('RAW:', r['description_raw'][:200]); print(); print('CLEAN:', r['description_clean'][:200])"
python3 -c "import json; [print(r['id'], r['description_clean_length'], repr(r['description_clean'][:60])) for r in map(json.loads, open('data/processed/jobvision_clean.jsonl', encoding='utf-8')) if not r['is_valid']]"
```

The 2 invalid rows (`1519306` = 13 chars, `1519390` = 15 chars) are kept in
the output with `is_valid=False` so Stage 4 can skip them at embed time.

## 6. Important Decisions and Notes

Intentionally NOT done (out of scope): recomputing `content_hash`; stripping
ZWNJ; Hazm on skills, company, location, category, or salary; Parquet output;
any FastAPI endpoint; salary parsing; language re-detection; fuzzy dedup;
chunking (Stage 3).

Assumptions and edge cases:

- Installed `hazm==0.10.0` `Normalizer()` takes no `remove_extra_spaces`
kwarg (verified via `inspect.signature`), so bare `Normalizer()` is used
and spacing is handled by our own collapse before/after Hazm.
- `Normalizer` is built once and reused for all records.
- `posted_date=None` stays `None`; only non-empty strings missing `Z` get it.
- `description_raw=None` or empty becomes `""`, still kept as invalid.
- Malformed JSONL lines are skipped with a stderr warning, not a crash.
- Sample CSV uses `utf-8-sig` (Excel-friendly); its `embed_text` is truncated  
to 2000 chars for readability while the JSONL keeps the full text.

