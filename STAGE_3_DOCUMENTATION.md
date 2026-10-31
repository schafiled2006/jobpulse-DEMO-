# Stage 3 — Chunking Decision

> Audience: JobPulse collaborators (owner + reviewer).
> Scope: `data/processed/jobvision_clean.jsonl` → `data/processed/stage3_*`.
> Stack: `transformers` (`BAAI/bge-m3` tokenizer only), `uv`, Python 3.11.
> Status: **code complete, real-tokenizer run pending** (see §3).

## 1. Stage Overview

Goal: decide — with measured evidence, not guessing — whether **one job ad can stay one chunk** for embedding, or whether long postings must be split.

Why it matters for RAG: Stage 4 embeds `embed_text` with `BAAI/bge-m3` (hard limit **8192 tokens**). If any ad exceeds that limit, its tail is silently truncated: skills and requirements disappear from the vector, retrieval (Stage 5) misses relevant jobs, and generation (Stage 6) hallucinates gaps. Stage 3 measures every ad with the **real BGE-M3 tokenizer** so Stage 4 can embed full texts with a correctly sized `max_seq_length` instead of the temporary `512`.

## 2. What Was Implemented

### Files created / modified

| Path | Status | Purpose |
| ---- | ------ | ------- |
| `backend/ingestion/chunk_analysis.py` | new (405 lines) | Read-only analysis + CLI (`analyze` / `main`) |
| `backend/tests/test_chunk_analysis.py` | new (165 lines) | 6 tests: 2 real-tokenizer (`slow`), 4 offline |
| `backend/pyproject.toml` (+ `uv.lock`) | modified | Added `transformers>=4.40`, registered `slow` marker |

### Main functions (`backend/ingestion/chunk_analysis.py`)

| Function | Responsibility |
| -------- | -------------- |
| `get_tokenizer()` | Load `BAAI/bge-m3` tokenizer once (lazy import; tokenizer only, never model weights) |
| `count_tokens(text, tokenizer)` | `len(tokenizer.encode(text, add_special_tokens=True))` — specials count toward the limit |
| `load_clean_records(path)` | Read JSONL; return `(valid, valid_count, invalid_count)`; malformed lines warn on stderr and skip |
| `percentile_sorted()` / `compute_stats()` | min / max / mean / p50 / p90 / p95 / p99 without numpy (linear interpolation) |
| `count_exceeding()` | Strict `>` counts for thresholds `(512, 1024, 2048, 4096, 8192)` |
| `build_report()` | Full `stage3_token_report.txt` text (header + both stat blocks + PASS/FAIL verdict) |
| `build_decision_markdown()` | `stage3_decision.md` with real numbers filled into the locked template |
| `analyze()` | Orchestration: count → stats → write 3 files → print → return summary dict (`breached_hard_limit`) |
| `main()` | CLI entry; exit `0` (all ≤ 8192) or `1` (breach = Stage 2 failure, or missing input) |

### Exact analysis steps (in order)

1. Load the BGE-M3 tokenizer **once** (`AutoTokenizer.from_pretrained("BAAI/bge-m3")`).
2. Read `data/processed/jobvision_clean.jsonl`; keep `is_valid == True` for stats, count `is_valid == False` as skipped.
3. For each valid record compute token counts for `embed_text` (primary) and `description_clean` (secondary) with `add_special_tokens=True`.
4. Compute min / max / mean / p50 / p90 / p95 / p99 and `>` counts for 512 / 1024 / 2048 / 4096 / 8192, for both fields.
5. Write the three output files (see §3); print the report to stdout.
6. Exit `0` if `max ≤ 8192`, else `1` (do **not** split — treat as Stage 2 data failure).

## 3. Input & Output

### Input

- Path: `data/processed/jobvision_clean.jsonl` (Stage 2 output, UTF-8 JSONL, never modified).
- At implementation time: **1989 records = 1987 valid + 2 invalid** (`1519306` = 13 chars, `1519390` = 15 chars, kept with `is_valid=False` so Stage 4 skips them).

### Outputs (`data/processed/`, git-ignored derived artifacts)

| File | Content |
| ---- | ------- |
| `stage3_token_report.txt` | Header (UTC stamp, model, input, total/valid/invalid, rule, thresholds) + `[embed_text]` block + `[description_clean]` block + `RESULT: PASS/FAIL` + outlier/decision pointers |
| `stage3_outliers.jsonl` | Records with `embed_text` tokens `> 4096` (`id`, `token_count`, `char_length`, `title_clean`, `embed_text_preview` ≤ 200 chars); empty file = none |
| `stage3_decision.md` | Locked decision + evidence table + verdict + consequences, all filled with measured numbers |

### Key statistics

> ⚠️ **Real BGE-M3 token numbers are PENDING.** `transformers` was added to `pyproject.toml`/`uv.lock` but was not yet installed in `backend/.venv`, and the `~/.cache/huggingface` tokenizer cache was absent, so the script has not run end-to-end with the real tokenizer. **Do not quote token stats until the run below completes.**

Character-length proxy from Stage 2 (`cleaning_report.txt`, **chars, not tokens** — scale only):

| field | min | max | mean |
| ----- | --: | --: | ---: |
| `embed_text` (chars) | 29 | 7019 | 843.6 |
| `description_clean` (chars) | 13 | 6992 | 795.3 |

After the first real run, fill in from `stage3_token_report.txt`:

```text
embed_text tokens: max=____, mean=____, p99=____
> 512: ____ | > 1024: ____ | > 2048: ____ | > 4096: ____ | > 8192: ____
RESULT: ____  | exit code: ____
```

## 4. How to Run

```bash
cd backend
uv sync                                     # installs transformers>=4.40 (also resolves torch stack; slow)
uv run python -m ingestion.chunk_analysis   # or: uv run python ingestion/chunk_analysis.py
echo $?                                     # 0 = PASS (all ≤ 8192), 1 = breach / missing input
cat ../data/processed/stage3_token_report.txt
wc -l ../data/processed/stage3_outliers.jsonl   # 0 lines = no outliers over 4096
```

Tests:

```bash
cd backend
uv run pytest tests/test_chunk_analysis.py -v              # 4 offline pass + 2 slow with tokenizer cache
uv run pytest tests/test_chunk_analysis.py -v -k "not slow"  # offline only, no download
```

First run downloads **~570 MB** of tokenizer files to `~/.cache/huggingface`; later runs reuse the cache. Only the tokenizer is loaded — never the full BGE-M3 weights.

## 5. Success Criteria & Validation

Success = **PASS**: `max(embed_text tokens) ≤ 8192` over all 1987 valid records → exit `0`, no splitting, decision locked.

Validate in ~3 minutes:

```bash
cat data/processed/stage3_token_report.txt       # check RESULT: PASS + threshold table
cat data/processed/stage3_decision.md            # check verdict + evidence table
wc -l data/processed/stage3_outliers.jsonl
md5sum data/processed/jobvision_clean.jsonl     # must be unchanged: c523010cb1379c5067d883533127af8a
```

Automated guard: `test_no_records_exceed_hard_limit` loads the real JSONL with the real tokenizer and asserts `max ≤ 8192`; `test_token_counter_includes_special_tokens` asserts `count_tokens("سلام") > 1`. Both are `slow`-marked and **skip** (not fail) when the tokenizer cache/input is unavailable, so offline CI stays green.

## 6. Important Decisions & Notes

- **Decision (locked): one job ad = one chunk.** Chunk text for Stage 4 = **`embed_text`** (`title_clean | skills | description_clean`).
- **Do not split any records.** Soft outlier threshold **4096 tokens** = flag for manual review only. Hard model limit **8192 tokens** (BGE-M3) = breach is a **Stage 2 data failure** (exit 1), fixed by re-cleaning source records, never by adding a splitter here.
- **Intentionally NOT done:** modifying `jobvision_clean.jsonl`; embedding anything; touching ChromaDB; changing Stage 4 `max_seq_length`; any split/overlap/chunker logic; loading model weights; any FastAPI endpoint.
- Assumptions / edge cases: thresholds are strict `>`; specials included (`add_special_tokens=True`); invalid records excluded from stats but counted in the header; blank/malformed JSONL lines skipped with stderr warning (Stage 2/4 policy); percentiles via linear interpolation (no numpy); outlier previews truncated to 200 chars; missing input → `ERROR` on stderr + exit 1.
- Verified at implementation time: `py_compile` clean; **8 passed, 2 skipped** (`test_chunk_analysis` offline 4 + `test_cleaner` 4; 2 slow skipped without `transformers`). `test_health` / `test_embed_and_index` collection errors in the same venv are pre-existing (missing `slowapi`/`chromadb` in the partial env) and unrelated to Stage 3.

## 7. Next Step

After the first real run confirms `> 8192 = 0`: in a **follow-up (not this stage)**, raise Stage 4 `max_seq_length` from the temporary `512` toward the BGE-M3 `8192` limit (the `> 512` count in the report quantifies how many ads are currently truncated), then **clean-rebuild the Chroma collection** (`--all`) and re-run retrieval spot-checks. Re-run Stage 3 after any Stage 2 re-clean.
