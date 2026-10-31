"""Stage 9 runner part 2b: timestamped JSON+Markdown report writer."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _json_safe(obj: Any) -> Any:
    """Recursively replace NaN/Infinity with ``None`` (strict JSON output)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def write_report(out_dir: Path, stamp: str, mode: str, top_k: int,
                 samples: list[dict[str, Any]], result: dict[str, Any]) -> Any:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": stamp, "mode": mode, "top_k": top_k,
               "n_samples": len(samples), "means": result["means"],
               "elapsed_s": result["elapsed_s"],
               "gemini_calls": result["gemini_calls"],
               "cache_hits": result["cache_hits"], "samples": result["rows"]}
    jp = out_dir / f"eval_{stamp}_{mode}.json"
    jp.write_text(
        json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    L = [f"# JobPulse Eval — {stamp} ({mode}, top_k={top_k})", "",
         f"- samples: {len(samples)} | elapsed: {result['elapsed_s']}s",
         f"- Gemini calls: {result['gemini_calls']} (cached: {result['cache_hits']})",
         "", "## Mean recall", "", "| k | recall |", "|---|--------|"]
    for k in sorted(result["means"]):
        v = result["means"][k]
        L.append(f"| {k} | {(f'{v:.3f}' if v is not None else 'n/a')} |")
    L += ["", "## Per-sample", "",
          "| id | domain | recall@5 | retrieved | missing expected |",
          "|----|--------|----------|-----------|------------------|"]
    for r in result["rows"]:
        r5 = r["recall"].get(5)
        r5s = f"{r5:.2f}" if isinstance(r5, float) and r5 == r5 else "n/a"
        L.append(f"| {r['id']} | {r.get('domain')} | {r5s} "
                 f"| {r['n_retrieved']} | {', '.join(r['missing_ids']) or '—'} |")
    if mode == "full":
        L += ["", "## Grounding", "", "| id | rate | ungrounded |",
              "|----|------|------------|"]
        for r in result["rows"]:
            g = r.get("grounding")
            if not g:
                continue
            rate = g["grounding_rate"]
            L.append(f"| {r['id']} | {(f'{rate:.2f}' if rate is not None else 'n/a')} "
                     f"| {', '.join(g['ungrounded'][:6]) or '—'} |")
    mp = out_dir / f"eval_{stamp}_{mode}.md"
    mp.write_text("\n".join(L) + "\n", encoding="utf-8")
    return jp, mp
