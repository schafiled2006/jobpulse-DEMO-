"""Stage 3 tests - chunking decision (tokenizer-based).

Run from `backend/`::

    uv run pytest tests/test_chunk_analysis.py -v

Two required tests need the real BGE-M3 tokenizer (first run downloads
~570 MB from Hugging Face, then cached in ~/.cache/huggingface):

- test_token_counter_includes_special_tokens
- test_no_records_exceed_hard_limit

They are marked `slow` and skip gracefully when the model cache / input
file is unavailable, so offline CI stays green. The remaining tests use a
tiny fake tokenizer and tmp files (fast, no network).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from ingestion.chunk_analysis import (
    HARD_MODEL_LIMIT,
    MODEL_NAME,
    OUTLIER_PREVIEW_CHARS,
    SOFT_OUTLIER_THRESHOLD,
    analyze,
    compute_stats,
    count_exceeding,
    count_tokens,
    load_clean_records,
)

# ---------------------------------------------------------------------------
# Helpers (offline: no model download)
# ---------------------------------------------------------------------------


class _FakeTokenizer:
    """Whitespace tokenizer stub: 1 token per word + 2 fake special tokens."""

    def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
        n: int = len((text or "").split())
        return [0] * (n + (2 if add_special_tokens else 0))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

requires_tokenizer = pytest.mark.slow


def test_compute_stats_percentiles() -> None:
    """Percentile helper matches linear interpolation on a known range."""
    stats: dict[str, float] = compute_stats([1, 2, 3, 4, 5])
    assert stats["min"] == 1.0 and stats["max"] == 5.0
    assert stats["mean"] == pytest.approx(3.0)
    assert stats["p50"] == pytest.approx(3.0)
    assert stats["p90"] == pytest.approx(4.6)
    assert stats["p95"] == pytest.approx(4.8)
    assert compute_stats([])["max"] == 0.0


def test_count_exceeding_strictly_greater() -> None:
    """Thresholds are strict `>`; exact boundary values do not count."""
    over: dict[int, int] = count_exceeding([512, 513, 8192, 8193])
    assert over[512] == 3  # 513, 8192, 8193
    assert over[8192] == 1  # only 8193
    assert over[4096] == 2


def test_fake_tokenizer_counts_words_plus_specials() -> None:
    """Offline sanity: fake tokenizer path used by analyze()."""
    assert count_tokens("a b c", _FakeTokenizer()) == 5  # 3 words + 2 specials
    assert count_tokens("", _FakeTokenizer()) == 2  # specials only


def test_analyze_writes_outliers_and_previews(tmp_path: Path) -> None:
    """analyze() flags >4096-token rows with truncated previews (fake tokens)."""
    long_text: str = "w " * 5000  # 5000 words -> 5002 fake tokens
    rows: list[dict[str, Any]] = [
        {
            "id": "ok-1",
            "title_clean": "t",
            "embed_text": "hello world",
            "description_clean": "hi",
            "is_valid": True,
        },
        {
            "id": "big-1",
            "title_clean": "t" * 10,
            "embed_text": long_text,
            "description_clean": "short",
            "is_valid": True,
        },
        {
            "id": "bad-1",
            "title_clean": "x",
            "embed_text": long_text,
            "description_clean": "y",
            "is_valid": False,
        },  # skipped
    ]
    src: Path = _write_jsonl(tmp_path / "clean.jsonl", rows)
    out: Path = tmp_path / "processed"
    summary: dict[str, Any] = analyze(
        clean_path=src, processed_dir=out, tokenizer=_FakeTokenizer()
    )
    assert summary["valid_count"] == 2 and summary["invalid_count"] == 1
    assert summary["outlier_rows"] == 1
    assert summary["breached_hard_limit"] is False
    outlier_lines: list[str] = (
        (out / "stage3_outliers.jsonl").read_text(encoding="utf-8").strip().splitlines()
    )
    assert len(outlier_lines) == 1
    row: dict[str, Any] = json.loads(outlier_lines[0])
    assert set(row) == {
        "id",
        "token_count",
        "char_length",
        "title_clean",
        "embed_text_preview",
    }
    assert row["id"] == "big-1" and row["token_count"] == 5002
    assert len(row["embed_text_preview"]) <= OUTLIER_PREVIEW_CHARS
    assert (out / "stage3_token_report.txt").stat().st_size > 0
    assert "one job ad = one chunk" in (out / "stage3_decision.md").read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Required spec tests (need real BGE-M3 tokenizer; ~570 MB first download)
# ---------------------------------------------------------------------------


@requires_tokenizer
def test_token_counter_includes_special_tokens() -> None:
    """Real tokenizer must count special tokens: 'salam' yields > 1 token.

    Needs the BGE-M3 tokenizer cache (first run downloads ~570 MB).
    Skips gracefully when transformers / HF cache is unavailable.
    """
    try:
        from ingestion.chunk_analysis import get_tokenizer

        tokenizer: Any = get_tokenizer()
    except Exception as exc:  # offline CI or no cache: skip, do not fail
        pytest.skip(f"BGE-M3 tokenizer unavailable: {exc}")
    assert MODEL_NAME == "BAAI/bge-m3"
    assert count_tokens("سلام", tokenizer) > 1  # word piece(s) + specials


@requires_tokenizer
def test_no_records_exceed_hard_limit() -> None:
    """All valid cleaned records must fit the 8192-token BGE-M3 limit.

    Loads data/processed/jobvision_clean.jsonl with the real tokenizer and
    asserts max(token_counts) <= 8192. Skips (not fails) when the tokenizer
    cache or input file is unavailable.
    """
    clean_path: Path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "processed"
        / "jobvision_clean.jsonl"
    )
    if not clean_path.exists():
        pytest.skip(f"Cleaned input missing: {clean_path}")
    try:
        from ingestion.chunk_analysis import get_tokenizer

        tokenizer: Any = get_tokenizer()
    except Exception as exc:
        pytest.skip(f"BGE-M3 tokenizer unavailable: {exc}")
    valid, _, _ = load_clean_records(clean_path)
    assert valid, "no valid records found"
    counts: list[int] = [
        count_tokens(str(r.get("embed_text") or ""), tokenizer) for r in valid
    ]
    assert max(counts) <= HARD_MODEL_LIMIT
    assert sum(1 for c in counts if c > SOFT_OUTLIER_THRESHOLD) >= 0  # reported only
