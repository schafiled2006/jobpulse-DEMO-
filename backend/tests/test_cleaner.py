"""Stage 2 tests - cleaner pipeline (no network, no files, fast).

Run from `backend/`::

    uv run pytest tests/test_cleaner.py -v
"""

from __future__ import annotations

from typing import Any

from hazm import Normalizer

from ingestion.cleaner import (
    build_embed_text,
    clean_record,
    collapse_whitespace,
    deduplicate_by_hash,
    normalize_skills,
    strip_html,
)


def _normalizer() -> Normalizer:
    """Build the real Hazm normalizer (same defaults as the pipeline)."""
    return Normalizer()


def test_html_stripping_keeps_persian_text_intact() -> None:
    """HTML tags are removed; Persian words and order survive."""
    raw: str = "<div dir=\"rtl\">چرم مشهد برای <strong>توسعه تیم</strong></div>"
    text: str = collapse_whitespace(strip_html(raw))
    assert "<" not in text and ">" not in text
    assert "چرم مشهد" in text
    assert "توسعه تیم" in text


def test_html_entities_are_decoded() -> None:
    """&nbsp; &amp; &lt; decode to real characters, not literal entities."""
    raw: str = "<p>حقوق&nbsp;و&nbsp;مزایا &amp; بیمه &lt;تست&gt;</p>"
    text: str = collapse_whitespace(strip_html(raw))
    assert "&nbsp;" not in text and "&amp;" not in text and "&lt;" not in text
    assert "&" in text  # &amp; -> &
    assert "حقوق" in text and "بیمه" in text


def test_skill_html_ampersand_preserved_literally() -> None:
    """'Html & CSS' keeps its ampersand; skills are stripped, never Hazm-ed."""
    skills: list[str] = normalize_skills(["Html & CSS", "  Python  ", "", 123, None])
    assert skills == ["Html & CSS", "Python"]
    assert "Html & CSS" in skills  # ampersand untouched
    embed: str = build_embed_text("توسعه‌دهنده", skills, "متن تستی طولانی کافی")
    assert "Html & CSS" in embed
    assert "&amp;" not in embed


def test_short_record_flagged_invalid_but_kept() -> None:
    """<20 chars after cleaning -> is_valid=False, record still in output."""
    raw: dict[str, Any] = {
        "id": "tiny-1",
        "title_raw": "تست",
        "description_raw": "<p>سلام</p>",
        "required_skills": [],
        "content_hash": "abc123",
        "posted_date": "2026-09-14T13:56:42",
        "language": "fa",
    }
    out: dict[str, Any] = clean_record(raw, _normalizer(), "2026-01-01T00:00:00Z")
    assert out["description_clean_length"] == len(out["description_clean"])
    assert out["description_clean_length"] < 20
    assert out["is_valid"] is False
    # Raw fields untouched; new fields present; hash recomputed never.
    assert out["description_raw"] == "<p>سلام</p>"
    assert out["content_hash"] == "abc123"
    assert out["posted_date"] == "2026-09-14T13:56:42Z"
    assert "title_clean" in out and "embed_text" in out and "cleaned_at" in out
    kept, dropped = deduplicate_by_hash([out])
    assert len(kept) == 1 and dropped == []  # still present after dedup
