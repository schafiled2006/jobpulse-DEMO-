"""Stage 3 - Chunking decision (read-only token analysis).

Confirms the locked decision **one job ad = one chunk** with chunk text
= ``embed_text`` by measuring real BGE-M3 token lengths over
``data/processed/jobvision_clean.jsonl`` (Stage 2 output).

Read-only: never modifies the cleaned JSONL. Writes three derived files
into ``data/processed/``:

- ``stage3_token_report.txt`` - full formatted token statistics.
- ``stage3_outliers.jsonl``   - one line per valid record with > 4096 tokens.
- ``stage3_decision.md``      - human-readable decision with real numbers.

Run from ``backend/``::

    uv run python -m ingestion.chunk_analysis
    uv run python ingestion/chunk_analysis.py

No CLI arguments. Exit code 0 if max tokens <= 8192 (BGE-M3 hard limit),
1 otherwise (treated as a Stage 2 failure - do NOT split records here).

NOTE (first run): ``AutoTokenizer.from_pretrained("BAAI/bge-m3")`` downloads
~570 MB of tokenizer files from Hugging Face on first use and caches them
locally (``~/.cache/huggingface``). Later runs reuse the cache.
Only the *tokenizer* is loaded - never the full model weights.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# backend/ingestion/chunk_analysis.py -> parents[2] is the repo root.
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
_DEFAULT_CLEAN_PATH: Path = _REPO_ROOT / "data" / "processed" / "jobvision_clean.jsonl"
_DEFAULT_PROCESSED_DIR: Path = _REPO_ROOT / "data" / "processed"

# Locked Stage 3 decision constants (do not change without a new decision doc).
MODEL_NAME: str = "BAAI/bge-m3"
SOFT_OUTLIER_THRESHOLD: int = 4096
HARD_MODEL_LIMIT: int = 8192
REPORT_THRESHOLDS: tuple[int, ...] = (512, 1024, 2048, 4096, 8192)
OUTLIER_PREVIEW_CHARS: int = 200


def get_tokenizer() -> Any:
    """Load the BGE-M3 tokenizer once (lazy import so module stays importable).

    WARNING: first run downloads ~570 MB from Hugging Face and caches it in
    ``~/.cache/huggingface``. Later runs are cached/offline.
    Only the tokenizer is needed - the full embedding weights are NOT loaded.
    """
    # Local import: lets unit tests with a fake tokenizer run without the dep,
    # while the real run fails loudly if transformers is missing.
    from transformers import AutoTokenizer  # type: ignore[import-not-found]

    # trust_remote_code is not needed for the bge-m3 tokenizer files.
    return AutoTokenizer.from_pretrained(MODEL_NAME)


def count_tokens(text: str, tokenizer: Any) -> int:
    """Count BGE-M3 tokens for ``text`` including special tokens.

    Mirrors Stage 4 embedding tokenization: ``add_special_tokens=True``
    (CLS/SEP-style tokens count toward the model limit, so they must count).
    """
    return len(tokenizer.encode(text or "", add_special_tokens=True))


def load_clean_records(
    clean_path: Path = _DEFAULT_CLEAN_PATH,
) -> tuple[list[dict[str, Any]], int, int]:
    """Read cleaned JSONL; return (valid_records, valid_count, invalid_count).

    Malformed lines are skipped with a stderr warning (same policy as the
    Stage 2/4 loaders). Records with ``is_valid == False`` are counted but
    excluded from token statistics.
    """
    if not clean_path.exists():
        raise FileNotFoundError(
            f"Cleaned input not found: {clean_path}. "
            "Expected Stage 2 output at data/processed/jobvision_clean.jsonl."
        )
    valid: list[dict[str, Any]] = []
    invalid_count: int = 0
    with clean_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"WARNING: skipping malformed line {line_no}: {exc}",
                    file=sys.stderr,
                )
                continue
            if rec.get("is_valid", True):
                valid.append(rec)
            else:
                invalid_count += 1
    return valid, len(valid), invalid_count


def percentile_sorted(sorted_vals: list[int], pct: float) -> float:
    """Linear-interpolation percentile over an already-sorted list (no numpy)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank: float = (pct / 100.0) * (len(sorted_vals) - 1)
    low: int = math.floor(rank)
    high: int = math.ceil(rank)
    if low == high:
        return float(sorted_vals[int(rank)])
    frac: float = rank - low
    return sorted_vals[low] * (1.0 - frac) + sorted_vals[high] * frac


def compute_stats(counts: list[int]) -> dict[str, float]:
    """Compute min/max/mean/p50/p90/p95/p99 over token counts."""
    if not counts:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        }
    ordered: list[int] = sorted(counts)
    return {
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "mean": sum(counts) / len(counts),
        "p50": percentile_sorted(ordered, 50),
        "p90": percentile_sorted(ordered, 90),
        "p95": percentile_sorted(ordered, 95),
        "p99": percentile_sorted(ordered, 99),
    }


def count_exceeding(
    counts: list[int], thresholds: tuple[int, ...] = REPORT_THRESHOLDS
) -> dict[int, int]:
    """Count records with token_count > each threshold (strictly greater)."""
    return {t: sum(1 for c in counts if c > t) for t in thresholds}


def _fmt_stat_block(
    field: str, counts: list[int], stats: dict[str, float], over: dict[int, int]
) -> list[str]:
    """Format one statistics block (embed_text or description_clean)."""
    n: int = len(counts)
    lines: list[str] = [
        f"[{field}] (n={n})",
        f"  min  : {stats['min']:.0f}",
        f"  max  : {stats['max']:.0f}",
        f"  mean : {stats['mean']:.1f}",
        f"  p50  : {stats['p50']:.1f}",
        f"  p90  : {stats['p90']:.1f}",
        f"  p95  : {stats['p95']:.1f}",
        f"  p99  : {stats['p99']:.1f}",
        "  exceeding thresholds (count, %):",
    ]
    for t in REPORT_THRESHOLDS:
        c: int = over.get(t, 0)
        pct: float = (100.0 * c / n) if n else 0.0
        lines.append(f"    > {t:>5d} : {c:>5d} ({pct:5.2f}%)")
    return lines


def build_report(
    total_records: int,
    valid_count: int,
    invalid_count: int,
    embed_counts: list[int],
    desc_counts: list[int],
    embed_stats: dict[str, float],
    desc_stats: dict[str, float],
    embed_over: dict[int, int],
    desc_over: dict[int, int],
) -> str:
    """Build the full human-readable token report (also printed to stdout)."""
    stamped: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines: list[str] = [
        "JobPulse Stage 3 - token-length report (BGE-M3 tokenizer)",
        "=========================================================",
        f"Generated (UTC) : {stamped}",
        f"Model           : {MODEL_NAME} (tokenizer only)",
        "Input           : data/processed/jobvision_clean.jsonl",
        f"Total records   : {total_records}",
        f"Valid (is_valid=True)  : {valid_count}",
        f"Invalid (skipped, kept in file): {invalid_count}",
        "Chunking rule   : one job ad = one chunk; chunk text = embed_text",
        f"Soft outlier threshold : {SOFT_OUTLIER_THRESHOLD} tokens",
        f"Hard model limit       : {HARD_MODEL_LIMIT} tokens (BGE-M3)",
        "",
    ]
    lines.extend(
        _fmt_stat_block(
            "embed_text (Stage 4 chunk text - primary)",
            embed_counts,
            embed_stats,
            embed_over,
        )
    )
    lines.append("")
    lines.extend(
        _fmt_stat_block(
            "description_clean (secondary)", desc_counts, desc_stats, desc_over
        )
    )
    lines.append("")
    over_hard: int = sum(1 for c in embed_counts if c > HARD_MODEL_LIMIT)
    if embed_stats.get("max", 0.0) > HARD_MODEL_LIMIT:
        lines.append(
            f"RESULT: FAIL - {over_hard} record(s) exceed hard limit "
            f"{HARD_MODEL_LIMIT}. Treat as Stage 2 failure (exit 1). "
            "Do NOT split here."
        )
    else:
        lines.append(
            f"RESULT: PASS - all {valid_count} valid records fit "
            f"within hard limit {HARD_MODEL_LIMIT}. No splitting needed."
        )
    soft_n: int = embed_over.get(SOFT_OUTLIER_THRESHOLD, 0)
    lines.append(
        f"Outliers (>{SOFT_OUTLIER_THRESHOLD} tokens): {soft_n} record(s) "
        "listed in stage3_outliers.jsonl (empty file = none)."
    )
    lines.append(
        "Decision: see stage3_decision.md for the locked one-chunk-per-ad ruling."
    )
    return "\n".join(lines) + "\n"


def build_decision_markdown(
    valid_count: int,
    invalid_count: int,
    embed_stats: dict[str, float],
    embed_over: dict[int, int],
    desc_stats: dict[str, float],
) -> str:
    """Build the human-readable decision document with real measured numbers."""
    stamped: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    over_512: int = embed_over.get(512, 0)
    over_4096: int = embed_over.get(SOFT_OUTLIER_THRESHOLD, 0)
    over_8192: int = embed_over.get(HARD_MODEL_LIMIT, 0)
    pct_512: float = (100.0 * over_512 / valid_count) if valid_count else 0.0
    if embed_stats.get("max", 0) > HARD_MODEL_LIMIT:
        verdict: str = (
            f"FAIL - {over_8192} record(s) exceed the {HARD_MODEL_LIMIT}-token hard limit. "
            "Per the locked rule this is a Stage 2 data failure: fix/clean the source "
            "records, do NOT implement splitting in Stage 3. Exiting non-zero."
        )
    else:
        verdict = (
            "PASS - one job ad = one chunk (chunk text = `embed_text`). "
            "No splitting, no overlap, no extra chunker. "
            f"All {valid_count} valid records fit within the "
            f"{HARD_MODEL_LIMIT}-token BGE-M3 limit."
        )
    out: list[str] = [
        "# JobPulse Stage 3 - Chunking Decision",
        "",
        f"> Generated (UTC): {stamped} | Model tokenizer: `{MODEL_NAME}` "
        "(tokenizer only) | Input: `data/processed/jobvision_clean.jsonl`",
        "",
        "## 1. Decision (locked)",
        "",
        "- **One job ad = one chunk.**",
        "- **Chunk text for Stage 4 = `embed_text`** "
        "(`title_clean | skills | description_clean`).",
        "- **Do not split any records.**",
        f"- Soft outlier threshold: **{SOFT_OUTLIER_THRESHOLD} tokens** (flag for review only).",
        f"- Hard model limit: **{HARD_MODEL_LIMIT} tokens** (BGE-M3). "
        "Any record above it is a Stage 2 failure (exit code 1).",
        "",
        f"## 2. Evidence (measured on {valid_count} valid + {invalid_count} invalid/skipped records)",
        "",
        "| metric | `embed_text` (primary) | `description_clean` (secondary) |",
        "|---|---|---|",
        f"| n | {valid_count} | {valid_count} |",
        f"| min | {embed_stats['min']:.0f} | {desc_stats['min']:.0f} |",
        f"| max | {embed_stats['max']:.0f} | {desc_stats['max']:.0f} |",
        f"| mean | {embed_stats['mean']:.1f} | {desc_stats['mean']:.1f} |",
        f"| p50 | {embed_stats['p50']:.1f} | {desc_stats['p50']:.1f} |",
        f"| p90 | {embed_stats['p90']:.1f} | {desc_stats['p90']:.1f} |",
        f"| p95 | {embed_stats['p95']:.1f} | {desc_stats['p95']:.1f} |",
        f"| p99 | {embed_stats['p99']:.1f} | {desc_stats['p99']:.1f} |",
        f"| count > 512 | {embed_over.get(512, 0)} | - |",
        f"| count > 1024 | {embed_over.get(1024, 0)} | - |",
        f"| count > 2048 | {embed_over.get(2048, 0)} | - |",
        f"| count > 4096 (outliers) | {over_4096} | - |",
        f"| count > 8192 (hard limit) | {over_8192} | - |",
        "",
        f"- Records over 512 tokens: **{over_512} ({pct_512:.2f}%)** - these would be "
        "truncated under the old temporary `max_seq_length=512` in Stage 4; "
        "Stage 3 confirms the limit must be raised after this decision "
        "(Stage 4 fix is out of scope here).",
        f"- Outlier file `stage3_outliers.jsonl` holds the {over_4096} record(s) over "
        f"{SOFT_OUTLIER_THRESHOLD} tokens (empty file = none) for manual inspection only.",
        "",
        "## 3. Verdict",
        "",
        verdict,
        "",
        "## 4. Consequences",
        "",
        "- Stage 4 keeps embedding the full `embed_text` per record "
        "(raise `max_seq_length` toward the BGE-M3 8192 limit in a follow-up; "
        "do not change it in this stage).",
        "- No chunker, splitter, overlap, or new config is added.",
        "- Re-run this analysis (`uv run python -m ingestion.chunk_analysis`) "
        "after any Stage 2 re-clean.",
        "",
    ]
    return "\n".join(out)


def analyze(
    clean_path: Path = _DEFAULT_CLEAN_PATH,
    processed_dir: Path = _DEFAULT_PROCESSED_DIR,
    tokenizer: Any | None = None,
) -> dict[str, Any]:
    """Run the full Stage 3 analysis; write report/outliers/decision; return summary.

    Loads records, counts tokens with the BGE-M3 tokenizer, computes stats,
    writes the three output files, and reports the hard-limit breach flag.
    ``tokenizer`` may be injected by tests (fake) to avoid the ~570 MB download.
    """
    owned: Any = tokenizer if tokenizer is not None else get_tokenizer()
    valid_records, valid_count, invalid_count = load_clean_records(clean_path)
    total_records: int = valid_count + invalid_count

    embed_counts: list[int] = [
        count_tokens(str(r.get("embed_text") or ""), owned) for r in valid_records
    ]
    desc_counts: list[int] = [
        count_tokens(str(r.get("description_clean") or ""), owned)
        for r in valid_records
    ]

    embed_stats: dict[str, float] = compute_stats(embed_counts)
    desc_stats: dict[str, float] = compute_stats(desc_counts)
    embed_over: dict[int, int] = count_exceeding(embed_counts)
    desc_over: dict[int, int] = count_exceeding(desc_counts)

    report: str = build_report(
        total_records,
        valid_count,
        invalid_count,
        embed_counts,
        desc_counts,
        embed_stats,
        desc_stats,
        embed_over,
        desc_over,
    )

    processed_dir.mkdir(parents=True, exist_ok=True)
    report_path: Path = processed_dir / "stage3_token_report.txt"
    outliers_path: Path = processed_dir / "stage3_outliers.jsonl"
    decision_path: Path = processed_dir / "stage3_decision.md"
    report_path.write_text(report, encoding="utf-8")

    # Outliers: valid records with embed tokens > 4096 (empty file = none).
    outlier_rows: int = 0
    with outliers_path.open("w", encoding="utf-8") as fh:
        for rec, n_tok in zip(valid_records, embed_counts):
            if n_tok > SOFT_OUTLIER_THRESHOLD:
                embed_text: str = str(rec.get("embed_text") or "")
                row: dict[str, Any] = {
                    "id": str(rec.get("id")),
                    "token_count": n_tok,
                    "char_length": len(embed_text),
                    "title_clean": str(rec.get("title_clean") or ""),
                    "embed_text_preview": embed_text[:OUTLIER_PREVIEW_CHARS],
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                outlier_rows += 1

    decision_path.write_text(
        build_decision_markdown(
            valid_count, invalid_count, embed_stats, embed_over, desc_stats
        ),
        encoding="utf-8",
    )

    print(report)
    print(f"Wrote report   -> {report_path}")
    print(f"Wrote outliers ({outlier_rows}) -> {outliers_path}")
    print(f"Wrote decision -> {decision_path}")

    breached: bool = bool(embed_counts) and max(embed_counts) > HARD_MODEL_LIMIT
    return {
        "total_records": total_records,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "embed_stats": embed_stats,
        "desc_stats": desc_stats,
        "embed_over": embed_over,
        "desc_over": desc_over,
        "outlier_rows": outlier_rows,
        "breached_hard_limit": breached,
        "report": report,
        "report_path": report_path,
        "outliers_path": outliers_path,
        "decision_path": decision_path,
    }


def main() -> int:
    """CLI entry point for `python -m ingestion.chunk_analysis`. Returns exit code."""
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    try:
        summary: dict[str, Any] = analyze()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    # Exit 1 if any record exceeds the 8192 hard limit (Stage 2 failure).
    return 1 if summary["breached_hard_limit"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
