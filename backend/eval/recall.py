"""Stage 9: recall@k for multi-expected golden samples (pure logic)."""
from __future__ import annotations

RECALL_KS: tuple[int, ...] = (1, 3, 5, 10)


def recall_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int) -> float:
    """نسبت expectedهای دیده‌شده در k تای اول؛ expected خالی -> NaN."""
    if not expected_ids:
        return float("nan")
    hits = len(set(expected_ids) & set(retrieved_ids[:k]))
    return hits / len(expected_ids)


def mean_recall(per_sample: dict[str, dict[int, float]], k: int) -> float | None:
    """میانگین روی نمونه‌های دارای expected (NaNها حذف می‌شوند)."""
    vals = [v[k] for v in per_sample.values() if v[k] == v[k]]
    return (sum(vals) / len(vals)) if vals else None
