"""Stage 2 - Clean & normalize raw JobVision postings.

Reads ``data/raw/jobvision_raw.jsonl`` (Stage 1 output), applies the exact
ordered pipeline from the Stage 2 brief, and writes cleaned JSONL + sample
CSV + report into ``data/processed/``.

Run from ``backend/``::

    uv run python -m ingestion.cleaner
    uv run python ingestion/cleaner.py

Locked stack: beautifulsoup4 for HTML stripping, hazm for Persian
normalization. Offline script - no FastAPI imports.
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from hazm import Normalizer

# backend/ingestion/cleaner.py -> parents[2] is the repo root.
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]
_BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
_DEFAULT_RAW_PATH: Path = _REPO_ROOT / "data" / "raw" / "jobvision_raw.jsonl"
_DEFAULT_PROCESSED_DIR: Path = _REPO_ROOT / "data" / "processed"

# Kept but flagged when shorter than this after cleaning.
_MIN_VALID_LENGTH: int = 20
_SAMPLE_SIZE: int = 20

# Collapse spaces/tabs only. Newlines and ZWNJ (U+200C) are preserved.
_WS_RUN_RE = re.compile(r"[ \t]+")


def strip_html(raw: str | None) -> str:
    """Strip HTML tags, decoding entities (&nbsp;/&amp;/&lt;...).

    ``separator=" "`` keeps block elements from gluing words together.
    """
    if not raw:
        return ""
    return BeautifulSoup(raw, "html.parser").get_text(separator=" ")


def collapse_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs to one space and strip the ends."""
    return _WS_RUN_RE.sub(" ", text).strip()


def normalize_skills(raw: Any) -> list[str]:
    """Strip skill strings only. No Hazm here, so "Html & CSS" is kept."""
    skills_raw: Any = raw if isinstance(raw, list) else []
    return [s.strip() for s in skills_raw if isinstance(s, str) and s.strip()]


def build_embed_text(title_clean: str, skills: list[str], desc_clean: str) -> str:
    """Build Stage 4 input: ``title | skills | description``."""
    if skills:
        return f"{title_clean} | {' | '.join(skills)} | {desc_clean}"
    return f"{title_clean} | {desc_clean}"


def fix_posted_date(value: Any) -> Any:
    """Append "Z" to ISO timestamps missing it; None stays None."""
    if isinstance(value, str) and value and not value.endswith("Z"):
        return value + "Z"
    return value

# __PART2__

def clean_record(
    raw: dict[str, Any],
    normalizer: Normalizer,
    cleaned_at: str,
) -> dict[str, Any]:
    """Apply the exact ordered Stage 2 pipeline to one raw record.

    1. copy fields 2. fix posted_date 3. strip HTML 4. collapse ws
    5. Hazm title+desc 6. collapse again 7. strip skills 8. embed_text
    9. lengths/is_valid 10. cleaned_at 11. (dedup happens in clean_all).
    """
    out: dict[str, Any] = dict(raw)  # 1. copy, keep raw/hash untouched
    out["posted_date"] = fix_posted_date(raw.get("posted_date"))  # 2.
    desc_text: str = collapse_whitespace(strip_html(raw.get("description_raw")))
    title_text: str = collapse_whitespace(str(raw.get("title_raw") or ""))
    # 5-6. Hazm on title+description only, then collapse again.
    desc_clean: str = collapse_whitespace(normalizer.normalize(desc_text))
    title_clean: str = collapse_whitespace(normalizer.normalize(title_text))
    skills: list[str] = normalize_skills(raw.get("required_skills"))  # 7.
    out["required_skills"] = skills
    out["title_clean"] = title_clean  # 8a.
    out["description_clean"] = desc_clean  # 8b.
    out["description_clean_length"] = len(desc_clean)  # 9a.
    out["embed_text"] = build_embed_text(title_clean, skills, desc_clean)  # 8c.
    out["is_valid"] = len(desc_clean) >= _MIN_VALID_LENGTH  # 9b.
    out["cleaned_at"] = cleaned_at  # 10.
    return out


def deduplicate_by_hash(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Any]]:
    """Drop later records sharing content_hash; keep first. Returns kept+ids."""
    seen: set[Any] = set()
    kept: list[dict[str, Any]] = []
    dropped_ids: list[Any] = []
    for rec in records:
        digest: Any = rec.get("content_hash")
        if digest in seen:
            dropped_ids.append(rec.get("id"))
            continue
        seen.add(digest)
        kept.append(rec)
    return kept, dropped_ids


def _describe(values: list[int]) -> tuple[int, int, float]:
    """Return (min, max, mean) for a non-empty int list."""
    return min(values), max(values), sum(values) / len(values)

# __PART3__

def build_report(
    *,
    input_count: int,
    kept_count: int,
    dropped_ids: list[Any],
    cleaned: list[dict[str, Any]],
) -> str:
    """Build the cleaning report string (printed to stdout + saved to file)."""
    valid: int = sum(1 for r in cleaned if r.get("is_valid"))
    invalid: int = kept_count - valid
    languages: Counter[str] = Counter(str(r.get("language")) for r in cleaned)
    desc_lens: list[int] = [int(r.get("description_clean_length", 0)) for r in cleaned]
    embed_lens: list[int] = [len(str(r.get("embed_text", ""))) for r in cleaned]
    lines: list[str] = [
        "JobPulse Stage 2 - cleaning report",
        "==================================",
        f"Input records (raw JSONL):        {input_count}",
        f"After dedup (kept):               {kept_count}",
        f"Dropped duplicates (hash):        {len(dropped_ids)}",
        f"is_valid=True  (>= {_MIN_VALID_LENGTH} chars): {valid}",
        f"is_valid=False (< {_MIN_VALID_LENGTH} chars):  {invalid}",
        "",
        "Language distribution (original `language` field):",
    ]
    for lang in sorted(languages):
        lines.append(f"  {lang}: {languages[lang]}")
    lines.append("")
    if desc_lens:
        dmin, dmax, dmean = _describe(desc_lens)
        lines.append(f"description_clean_length: min={dmin} max={dmax} mean={dmean:.1f}")
    if embed_lens:
        emin, emax, emean = _describe(embed_lens)
        lines.append(f"embed_text length:        min={emin} max={emax} mean={emean:.1f}")
    lines.append("")
    if dropped_ids:
        preview: str = ", ".join(str(i) for i in dropped_ids[:20])
        more: str = f" (+{len(dropped_ids) - 20} more)" if len(dropped_ids) > 20 else ""
        lines.append(f"Dropped duplicate ids (sample): {preview}{more}")
    else:
        lines.append("Dropped duplicate ids: none")
    return "\n".join(lines) + "\n"


def write_sample_csv(
    cleaned: list[dict[str, Any]],
    csv_path: Path,
    sample_size: int = _SAMPLE_SIZE,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Write a stratified sample (by original `language`) for human review.

    Proportional allocation over language strata with a fixed seed keeps the
    sample deterministic. Rounds to exactly `sample_size` rows.
    """
    rng = random.Random(seed)
    if len(cleaned) <= sample_size:
        sample: list[dict[str, Any]] = list(cleaned)
    else:
        strata: dict[str, list[int]] = {}
        for idx, rec in enumerate(cleaned):
            strata.setdefault(str(rec.get("language")), []).append(idx)
        total: int = len(cleaned)
        picked: set[int] = set()
        for lang in sorted(strata):
            share: int = min(len(strata[lang]), max(1, round(len(strata[lang]) / total * sample_size)))
            picked.update(rng.sample(strata[lang], share))
        # Fix rounding drift to reach exactly sample_size.
        ordered: list[int] = sorted(picked)
        if len(ordered) > sample_size:
            ordered = sorted(rng.sample(ordered, sample_size))
        while len(ordered) < sample_size:
            cand: int = rng.randrange(total)
            if cand not in picked:
                picked.add(cand)
                ordered = sorted(picked)
        sample = [cleaned[i] for i in ordered[:sample_size]]
    fieldnames: list[str] = [
        "id", "language", "title_raw", "title_clean",
        "description_clean_length", "is_valid", "required_skills",
        "embed_text", "content_hash", "source_url",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in sample:
            row: dict[str, Any] = dict(rec)
            skills: Any = row.get("required_skills", [])
            row["required_skills"] = " | ".join(skills) if isinstance(skills, list) else skills
            row["embed_text"] = str(row.get("embed_text", ""))[:2000]
            writer.writerow(row)
    return sample

# __PART4__

def clean_file(
    raw_path: Path = _DEFAULT_RAW_PATH,
    processed_dir: Path = _DEFAULT_PROCESSED_DIR,
) -> dict[str, Any]:
    """Read raw JSONL, write cleaned JSONL + sample CSV + report. Return stats."""
    if not raw_path.exists():
        raise FileNotFoundError(
            f"Raw input not found: {raw_path}. "
            "Expected Stage 1 output at data/raw/jobvision_raw.jsonl."
        )
    processed_dir.mkdir(parents=True, exist_ok=True)
    raw_records: list[dict[str, Any]] = []
    with raw_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw_records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARNING: skipping malformed line {line_no}: {exc}", file=sys.stderr)
    # Hazm Normalizer is costly: build ONCE. Installed hazm==0.10 takes no
    # `remove_extra_spaces` kwarg, so spacing is handled by our own
    # collapse_whitespace before/after normalize (spec steps 4 and 6).
    normalizer = Normalizer()
    cleaned_at: str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cleaned_all: list[dict[str, Any]] = [
        clean_record(r, normalizer, cleaned_at) for r in raw_records
    ]
    kept, dropped_ids = deduplicate_by_hash(cleaned_all)
    jsonl_path: Path = processed_dir / "jobvision_clean.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for rec in kept:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sample: list[dict[str, Any]] = write_sample_csv(
        kept, processed_dir / "jobvision_clean_sample.csv"
    )
    report: str = build_report(
        input_count=len(raw_records), kept_count=len(kept),
        dropped_ids=dropped_ids, cleaned=kept,
    )
    report_path: Path = processed_dir / "cleaning_report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {len(kept)} records -> {jsonl_path}")
    print(f"Wrote {len(sample)} sample rows -> {processed_dir / 'jobvision_clean_sample.csv'}")
    print(f"Wrote report -> {report_path}")
    return {
        "input_count": len(raw_records), "kept_count": len(kept),
        "dropped_ids": dropped_ids, "jsonl_path": jsonl_path, "report": report,
    }


def main() -> None:
    """CLI entry point for `python -m ingestion.cleaner` and direct runs."""
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    clean_file()


if __name__ == "__main__":
    main()
