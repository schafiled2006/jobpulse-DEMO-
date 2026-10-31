"""Quick verification script for Stage 4 Embed & Index search quality."""

from __future__ import annotations

import io
import sys

from app.retrieval.retrieval import retrieve_matched_jobs

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

QUERIES = [
    "برنامه نویس پایتون و جنگو با تجربه دیتابیس و داکر",
    "Machine Learning and NLP Engineer with Python and deep learning",
    "توسعه‌دهنده فرانت‌اند React و TypeScript",
    "کارشناس حسابداری و مالی مسلط به اکسل و قوانین مالیاتی",
]

for query in QUERIES:
    print("\n" + "=" * 70)
    print(f"QUERY: {query}")
    print("=" * 70)
    matches = retrieve_matched_jobs(query, top_k=3)
    for idx, job in enumerate(matches, 1):
        print(f"[{idx}] Score: {job['similarity_score']:.4f} | {job['title']} ({job['company']})")
        if job.get("skills"):
            print(f"    Skills: {job['skills']}")
        print(f"    Category: {job.get('category', '')}")
