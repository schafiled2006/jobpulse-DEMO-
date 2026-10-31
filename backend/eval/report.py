"""Stage 9 runner part 2a: evaluation loop."""
from __future__ import annotations

import sys
import time
from typing import Any


def run_evaluation(
    samples: list[dict[str, Any]],
    mode: str,
    top_k: int,
    recall_mod: Any,
    cache_mod: Any,
    grounding_mod: Any,
) -> dict[str, Any]:
    """حلقه اصلی: retrieval برای همه؛ generation فقط در mode=full."""
    from app.retrieval.retrieval import retrieve_matched_jobs

    gen_fn = None
    if mode == "full":
        from app.retrieval.generation import generate_gap_analysis
        gen_fn = generate_gap_analysis

    ks = recall_mod.RECALL_KS
    per_sample: dict[str, dict[int, float]] = {}
    rows: list[dict[str, Any]] = []
    gemini_calls = cache_hits = 0
    t0 = time.perf_counter()
    for s in samples:
        sid = str(s["id"])
        expected = [str(x) for x in (s.get("expected_job_ids") or [])]
        try:
            matched = retrieve_matched_jobs(str(s["resume_text"]), top_k=top_k)
        except Exception as exc:  # one bad sample must not kill the whole run
            print(f"[eval] retrieval failed for {sid}: {exc}", file=sys.stderr)
            matched = []
        rids = [str(m["id"]) for m in matched]
        rec = {k: round(recall_mod.recall_at_k(rids, expected, k), 4) for k in ks}
        per_sample[sid] = rec
        row: dict[str, Any] = {
            "id": sid, "lang": s.get("lang"), "domain": s.get("domain"),
            "n_expected": len(expected), "n_retrieved": len(rids),
            "recall": rec, "retrieved_ids": rids,
            "retrieved_titles": [str(m.get("title", ""))[:60] for m in matched],
            "expected_ids": expected,
            "missing_ids": [e for e in expected if e not in rids[: max(ks)]],
        }
        if mode == "full" and matched:
            key = cache_mod.cache_key(str(s["resume_text"]), rids)
            gap = cache_mod.load_cache(key) if cache_mod.use_cache else None
            cached = gap is not None
            if gap is None:
                try:
                    gap = gen_fn(str(s["resume_text"]), matched)
                except Exception as exc:  # keep evaluating even if Gemini fails
                    print(f"[eval] generation failed for {sid}: {exc}", file=sys.stderr)
                    gap = {}
                gemini_calls += 1
                # Never cache empty results (e.g. missing API key) — they would
                # poison the cache and hide future successful runs.
                if gap and cache_mod.use_cache:
                    cache_mod.save_cache(key, gap)
            else:
                cache_hits += 1
            skills = list(gap.get("matching_skills", [])) + list(gap.get("missing_skills", []))
            g = grounding_mod.check_grounding(skills, matched)
            row["gap_analysis"] = gap
            row["gemini_cached"] = cached
            row["grounding"] = {
                "total": g["total"], "grounding_rate": g["grounding_rate"],
                "grounded": g["grounded"], "ungrounded": g["ungrounded"],
                "details": g["details"],
            }
        rows.append(row)
    elapsed = time.perf_counter() - t0
    means = {f"recall@{k}": recall_mod.mean_recall(per_sample, k) for k in ks}
    return {"means": means, "rows": rows, "elapsed_s": round(elapsed, 1),
            "gemini_calls": gemini_calls, "cache_hits": cache_hits}
