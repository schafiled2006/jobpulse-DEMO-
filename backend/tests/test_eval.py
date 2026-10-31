"""Stage 9 tests – Evaluation pipeline (fast, mocked retrieval/generation).

Run from `backend/`:

    uv run pytest tests/test_eval.py -v
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from eval import grounding as grounding_mod
from eval import recall as recall_mod
from eval import run_eval as run_eval_mod
from eval.grounding import check_grounding, normalize_skill_text
from eval.metrics import GOLDEN_SET_PATH, load_golden_set
from eval.recall import mean_recall, recall_at_k
from eval.report import run_evaluation
from eval.writer import write_report

# ---------------------------------------------------------------------------
# Shared data for the mocked evaluation loop
# ---------------------------------------------------------------------------

_SAMPLES: list[dict[str, Any]] = [
    {
        "id": "s-backend",
        "lang": "fa",
        "domain": "backend",
        "resume_text": "رزومه بک‌اند",
        "expected_job_ids": ["j1", "j2"],
    },
    {
        "id": "s-frontend",
        "lang": "en",
        "domain": "frontend",
        "resume_text": "frontend resume",
        "expected_job_ids": ["j9"],
    },
]

_RETRIEVED: dict[str, list[dict[str, Any]]] = {
    "رزومه بک‌اند": [
        {"id": "j1", "title": "برنامه‌نویس پایتون", "similarity_score": 0.9},
        {"id": "j3", "title": "کارشناس شبکه", "similarity_score": 0.5},
    ],
    "frontend resume": [
        {"id": "j9", "title": "برنامه‌نویس فرانت‌اند", "similarity_score": 0.8},
    ],
}


def _fake_retrieve(resume_text: str, top_k: int = 10) -> list[dict[str, Any]]:
    """Deterministic stand-in for ``retrieve_matched_jobs``."""
    return _RETRIEVED.get(resume_text, [])[:top_k]


@pytest.fixture(autouse=True)
def _cache_flag_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with the Gemini cache enabled (``main()`` may flip it)."""
    monkeypatch.setattr(run_eval_mod, "use_cache", True)


# ---------------------------------------------------------------------------
# Golden set (data/eval/golden_set.yaml)
# ---------------------------------------------------------------------------


def test_load_golden_set_shipped_file() -> None:
    """The shipped golden set must satisfy the Stage 9 contract of PROJECT_CONTEXT."""
    samples = load_golden_set()

    # PROJECT_CONTEXT asks for a labeled set of 15-20 resume -> jobs samples.
    assert len(samples) >= 15

    ids = [str(s["id"]) for s in samples]
    assert len(ids) == len(set(ids)), "golden-set ids must be unique"

    with_expected = 0
    for sample in samples:
        assert sample.get("resume_text"), f"{sample['id']}: empty resume_text"
        assert isinstance(sample["expected_job_ids"], list)
        if sample["expected_job_ids"]:
            with_expected += 1
    # Edge samples (e.g. rare skills) may legitimately expect zero matches.
    assert with_expected >= 12


def test_load_golden_set_parses_tmp_file(tmp_path: Path) -> None:
    """Parser handles block resumes, inline id lists, comments and notes."""
    golden = tmp_path / "golden.yaml"
    golden.write_text(
        "# comment line\n"
        "version: 1\n"
        "samples:\n"
        '  - id: "one"\n'
        '    lang: "fa"\n'
        '    domain: "backend"\n'
        "    resume_text: >-\n"
        "      سلام دنیا\n"
        "      خط دوم\n"
        '    expected_job_ids: ["10", "20"]\n'
        '    notes: "یادداشت"\n',
        encoding="utf-8",
    )

    samples = load_golden_set(golden)
    assert len(samples) == 1
    assert samples[0]["id"] == "one"
    assert samples[0]["resume_text"] == "سلام دنیا خط دوم"
    assert samples[0]["expected_job_ids"] == ["10", "20"]
    assert samples[0]["notes"] == "یادداشت"


def test_golden_ids_exist_in_dataset() -> None:
    """Every expected id must still exist (and be valid) in the cleaned dataset."""
    dataset = Path(__file__).resolve().parents[2] / "data" / "processed" / "jobvision_clean.jsonl"
    if not dataset.exists():
        pytest.skip("data/processed/jobvision_clean.jsonl not present")

    valid_ids: set[str] = set()
    with dataset.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("is_valid"):
                valid_ids.add(str(rec.get("id")))

    checked = 0
    for sample in load_golden_set():
        for jid in sample["expected_job_ids"]:
            checked += 1
            assert str(jid) in valid_ids, f"{sample['id']}: unknown job id {jid}"
    assert checked >= 12


# ---------------------------------------------------------------------------
# recall@k
# ---------------------------------------------------------------------------


def test_recall_at_k_counts_only_top_k() -> None:
    assert recall_at_k(["a", "b", "c"], ["a", "c"], 3) == 1.0
    assert recall_at_k(["a", "b", "c"], ["a"], 1) == 1.0
    # "a" is on position 3 — outside k=2, so nothing is hit.
    assert recall_at_k(["x", "y", "a"], ["a"], 2) == 0.0
    assert recall_at_k([], ["a"], 5) == 0.0


def test_recall_at_k_empty_expected_is_nan() -> None:
    assert math.isnan(recall_at_k(["a"], [], 5))


def test_mean_recall_filters_nan_and_handles_all_nan() -> None:
    per_sample: dict[str, dict[int, float]] = {
        "a": {1: 1.0, 3: 1.0},
        "b": {1: float("nan"), 3: 0.0},
    }
    assert mean_recall(per_sample, 1) == 1.0  # NaN sample dropped
    assert mean_recall(per_sample, 3) == 0.5
    assert mean_recall({"b": {1: float("nan")}}, 1) is None


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

_GROUNDING_JOBS: list[dict[str, Any]] = [
    {
        "id": "j1",
        "title": "برنامه‌نویس پایتون",
        "description_clean": "کار با Django و طراحی REST API و تحویل سریع و fast delivery",
        "category": "IT",
    },
]


def test_normalize_skill_text_unifies_variants() -> None:
    assert normalize_skill_text("Python") == "python"
    assert normalize_skill_text("Rest-API") == "rest api"
    # Arabic yeh -> Persian yeh, Persian digits -> ASCII, ZWNJ -> space.
    assert normalize_skill_text("پايتون") == "پایتون"
    assert normalize_skill_text("نسخه ۲۰۲۴") == "نسخه 2024"
    assert normalize_skill_text("نیم\u200cفاصله") == "نیم فاصله"


def test_check_grounding_reports_rate_and_methods() -> None:
    skills = ["Python", "Django", "Fast API", "Kubernetes"]
    report = check_grounding(skills, _GROUNDING_JOBS)

    assert report["total"] == 4
    assert report["grounding_rate"] == 0.75
    assert sorted(report["grounded"]) == ["Django", "Fast API", "Python"]
    assert report["ungrounded"] == ["Kubernetes"]
    # Persian variant of "Python" is present in the job title.
    assert report["details"]["Python"]["method"] == "variant"
    assert report["details"]["Django"]["method"] == "exact"
    # "fast" and "api" both appear separately -> token-level match.
    assert report["details"]["Fast API"]["method"] == "token"
    assert report["details"]["Kubernetes"]["jobs"] == []


def test_check_grounding_empty_skills_returns_none_rate() -> None:
    report = check_grounding([], _GROUNDING_JOBS)
    assert report["grounding_rate"] is None
    assert report["total"] == 0


# ---------------------------------------------------------------------------
# Evaluation loop (eval.report) — retrieval/generation fully mocked
# ---------------------------------------------------------------------------


def test_run_evaluation_retrieval_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.retrieval.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "retrieve_matched_jobs", _fake_retrieve)

    result = run_evaluation(_SAMPLES, "retrieval", 5, recall_mod, run_eval_mod, grounding_mod)

    # s-backend: j1 hit at rank 1 of 2 expected -> 0.5; s-frontend: 1.0.
    assert result["means"]["recall@1"] == 0.75
    assert result["means"]["recall@10"] == 0.75
    assert result["gemini_calls"] == 0
    assert result["cache_hits"] == 0
    assert result["elapsed_s"] >= 0

    rows = {r["id"]: r for r in result["rows"]}
    assert rows["s-backend"]["retrieved_ids"] == ["j1", "j3"]
    assert rows["s-backend"]["missing_ids"] == ["j2"]
    assert rows["s-frontend"]["missing_ids"] == []


def test_run_evaluation_survives_retrieval_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.retrieval.retrieval as retrieval_mod

    def _boom(resume_text: str, top_k: int = 10) -> list[dict[str, Any]]:
        raise RuntimeError("chroma down")

    monkeypatch.setattr(retrieval_mod, "retrieve_matched_jobs", _boom)

    result = run_evaluation(_SAMPLES, "retrieval", 5, recall_mod, run_eval_mod, grounding_mod)

    # One bad sample must not kill the run: rows are recorded as empty hits.
    assert len(result["rows"]) == 2
    assert all(r["retrieved_ids"] == [] for r in result["rows"])
    assert result["means"]["recall@1"] == 0.0


def test_run_evaluation_full_mode_caches_gemini(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.retrieval.generation as generation_mod
    import app.retrieval.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "retrieve_matched_jobs", _fake_retrieve)
    monkeypatch.setattr(run_eval_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(run_eval_mod, "use_cache", True)

    calls = {"n": 0}

    def _fake_generate(resume_text: str, matched: list[dict]) -> dict[str, Any]:
        calls["n"] += 1
        return {"matching_skills": ["Python"], "missing_skills": ["Kubernetes"], "summary": "خلاصه"}

    monkeypatch.setattr(generation_mod, "generate_gap_analysis", _fake_generate)

    first = run_evaluation(_SAMPLES, "full", 5, recall_mod, run_eval_mod, grounding_mod)
    assert first["gemini_calls"] == 2
    assert first["cache_hits"] == 0
    assert calls["n"] == 2

    row = first["rows"][0]
    assert row["gap_analysis"]["summary"] == "خلاصه"
    # "Python" appears in j1's title (Persian variant), "Kubernetes" nowhere.
    assert row["grounding"]["grounding_rate"] == 0.5

    # Second run must be served entirely from the on-disk cache.
    second = run_evaluation(_SAMPLES, "full", 5, recall_mod, run_eval_mod, grounding_mod)
    assert second["gemini_calls"] == 0
    assert second["cache_hits"] == 2
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Report writer (eval.writer)
# ---------------------------------------------------------------------------


def test_write_report_strict_json_and_markdown(tmp_path: Path) -> None:
    rows = [
        {
            "id": "s1", "domain": "backend",
            "recall": {1: 0.5, 5: float("nan")},
            "n_retrieved": 2, "missing_ids": ["j2"],
            "retrieved_ids": ["j1"], "retrieved_titles": ["t1"],
            "expected_ids": ["j1", "j2"],
        },
        {
            "id": "s2", "domain": "frontend",
            "recall": {1: 1.0, 5: 1.0},
            "n_retrieved": 1, "missing_ids": [],
            "retrieved_ids": ["j9"], "retrieved_titles": ["t9"],
            "expected_ids": ["j9"],
        },
    ]
    result = {
        "means": {"recall@1": 0.75, "recall@5": float("nan")},
        "rows": rows, "elapsed_s": 1.2,
        "gemini_calls": 0, "cache_hits": 0,
    }

    json_path, md_path = write_report(
        tmp_path, "20261010-120000", "retrieval", 10, _SAMPLES, result,
    )

    raw = json_path.read_text(encoding="utf-8")
    assert "NaN" not in raw  # non-finite floats must serialise as null
    payload = json.loads(raw)
    assert payload["mode"] == "retrieval"
    assert payload["top_k"] == 10
    assert payload["n_samples"] == 2
    assert payload["means"]["recall@5"] is None

    md = md_path.read_text(encoding="utf-8")
    assert "## Mean recall" in md
    assert "| s1 | backend | n/a |" in md
    assert "| s2 | frontend | 1.00 |" in md


# ---------------------------------------------------------------------------
# CLI (eval.run_eval / eval.cli)
# ---------------------------------------------------------------------------


def test_main_retrieval_mode_writes_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import app.retrieval.retrieval as retrieval_mod

    monkeypatch.setattr(retrieval_mod, "retrieve_matched_jobs", _fake_retrieve)

    rc = run_eval_mod.main(
        [
            "--mode", "retrieval",
            "--top-k", "5",
            "--limit", "2",
            "--golden", str(GOLDEN_SET_PATH),
            "--out", str(tmp_path),
        ]
    )

    assert rc == 0
    json_files = list(tmp_path.glob("eval_*_retrieval.json"))
    md_files = list(tmp_path.glob("eval_*_retrieval.md"))
    assert len(json_files) == 1 and len(md_files) == 1

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "retrieval"
    assert payload["top_k"] == 5
    assert payload["n_samples"] == 2


def test_main_rejects_bad_input(tmp_path: Path) -> None:
    assert run_eval_mod.main(["--top-k", "0"]) == 1

    empty = tmp_path / "empty.yaml"
    empty.write_text("# no samples here\n", encoding="utf-8")
    assert run_eval_mod.main(["--golden", str(empty)]) == 1

    missing = tmp_path / "does_not_exist.yaml"
    assert run_eval_mod.main(["--golden", str(missing)]) == 1


def test_main_no_cache_flag_flips_global(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("# none\n", encoding="utf-8")
    assert run_eval_mod.main(["--no-cache", "--golden", str(empty)]) == 1
    assert run_eval_mod.use_cache is False


def test_cli_entry_reuses_run_eval_main() -> None:
    import eval.cli as cli_mod

    assert cli_mod.main is run_eval_mod.main
