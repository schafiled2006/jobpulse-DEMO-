"""Stage 9 runner: CLI args, Gemini-response cache, wiring and entry point.

Run from ``backend/``::

    uv run python -m eval.cli --mode retrieval   # offline: recall@k only
    uv run python -m eval.cli --mode full        # + Gemini gap analysis & grounding

The evaluation loop lives in ``eval.report`` and the report writer in
``eval.writer``; this module parses arguments, loads the golden set, runs the
loop and prints a summary. Direct execution (``uv run python eval/run_eval.py``)
works as well because of the ``sys.path`` bootstrap below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import grounding as grounding_mod  # noqa: E402
from eval import recall as recall_mod  # noqa: E402
from eval import report as report_mod  # noqa: E402
from eval import writer as writer_mod  # noqa: E402
from eval.metrics import GOLDEN_SET_PATH, load_golden_set  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "eval" / "reports"

# ``eval.report.run_evaluation`` receives *this module* as ``cache_mod`` and
# reads ``use_cache`` from it, so the flag must stay a module-level global
# (updated by ``main()`` when ``--no-cache`` is passed).
use_cache: bool = True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (``argv=None`` reads ``sys.argv[1:]``)."""
    p = argparse.ArgumentParser(prog="eval", description="JobPulse Stage 9 evaluation")
    p.add_argument(
        "--mode",
        choices=["retrieval", "full"],
        default="retrieval",
        help="retrieval = recall@k only (offline); "
        "full = + Gemini gap analysis and grounding check",
    )
    p.add_argument("--golden", type=Path, default=GOLDEN_SET_PATH, help="golden-set YAML path")
    p.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="retrieval depth, i.e. how many jobs are fetched per resume (default: 10)",
    )
    p.add_argument("--limit", type=int, default=0, help="evaluate only the first N samples (0 = all)")
    p.add_argument("--no-cache", action="store_true", help="bypass the on-disk Gemini response cache")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"report output directory (default: {DEFAULT_REPORT_DIR})",
    )
    return p.parse_args(argv)


def cache_key(resume: str, job_ids: list[str]) -> str:
    """Stable cache key: resume text + the retrieved job ids (order-free)."""
    h = hashlib.sha256()
    h.update(resume.encode("utf-8"))
    h.update(b"\x00")
    h.update(",".join(sorted(job_ids)).encode("utf-8"))
    return h.hexdigest()[:16]


def load_cache(key: str) -> dict[str, Any] | None:
    fp = CACHE_DIR / f"{key}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_cache(key: str, val: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(val, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Load the golden set, run the evaluation loop and write the reports."""
    args = parse_args(argv)

    if args.top_k < 1:
        print("--top-k must be >= 1", file=sys.stderr)
        return 1

    global use_cache
    use_cache = not args.no_cache

    try:
        samples = load_golden_set(args.golden)
    except OSError as exc:
        print(f"Cannot read golden set {args.golden}: {exc}", file=sys.stderr)
        return 1
    if args.limit > 0:
        samples = samples[: args.limit]
    if not samples:
        print(f"No usable samples in {args.golden}", file=sys.stderr)
        return 1

    if args.mode == "full" and not os.environ.get("GEMINI_API_KEY"):
        print(
            "WARNING: GEMINI_API_KEY is not set — gap analyses will be empty "
            "and grounding rates 'n/a'.",
            file=sys.stderr,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = args.out or DEFAULT_REPORT_DIR

    # ``sys.modules[__name__]`` exposes cache_key/load_cache/save_cache/use_cache
    # under the name ``report.run_evaluation`` expects (``cache_mod``).
    result = report_mod.run_evaluation(
        samples,
        args.mode,
        args.top_k,
        recall_mod,
        sys.modules[__name__],
        grounding_mod,
    )
    json_path, md_path = writer_mod.write_report(
        out_dir, stamp, args.mode, args.top_k, samples, result,
    )

    print(f"== JobPulse Stage 9 eval ({args.mode}, top_k={args.top_k}) ==")
    print(
        f"samples: {len(samples)} | elapsed: {result['elapsed_s']}s | "
        f"Gemini calls: {result['gemini_calls']} (cached: {result['cache_hits']})"
    )
    for name in sorted(result["means"]):
        value = result["means"][name]
        text = f"{value:.3f}" if value is not None else "n/a"
        print(f"{name:>9}: {text}")
    print(f"report:  {json_path}")
    print(f"         {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
