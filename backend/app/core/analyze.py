"""Stage 5+6 integration – End-to-end resume analysis pipeline.

Chains the **retrieval** step (Stage 5: embed resume → query ChromaDB) with the
**generation** step (Stage 6: send resume + matched jobs to Gemini → skill-gap
report) into a single :func:`analyze_resume` call.

This module is the main entry point that Stage 7 (``POST /analyze``) will wrap
behind a FastAPI endpoint.

Usage::

    from app.core.analyze import analyze_resume

    result = analyze_resume(resume_text)
    # result == {"matched_jobs": [...], "gap_analysis": {...}}
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.retrieval.generation import generate_gap_analysis
from app.retrieval.retrieval import retrieve_matched_jobs

logger = logging.getLogger(__name__)


def analyze_resume(
    resume_text: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Run the full resume-analysis pipeline: retrieval → generation.

    Parameters
    ----------
    resume_text:
        Raw or extracted text of the candidate's resume (Persian, English, or
        mixed).
    top_k:
        Maximum number of matching job postings to retrieve from ChromaDB
        before passing them to the LLM for gap analysis. Default is 5,
        matching the ``POST /analyze`` default; the endpoint clamps clients
        to 1–10 so Gemini latency/token usage on the free tier stays bounded
        (Stage 6 recommends 3–5).

    Returns
    -------
    dict[str, Any]
        Always returns a dict with exactly two top-level keys::

            {
                "matched_jobs": [
                    {
                        "id": str,
                        "title": str,
                        "company": str,
                        "similarity_score": float,   # 0.0–1.0
                        "source_url": str,
                        "description_clean": str,
                    },
                    ...
                ],
                "gap_analysis": {
                    "matching_skills": [str, ...],
                    "missing_skills": [str, ...],
                    "summary": str,              # Persian paragraph
                },
            }

        On edge cases (empty resume, empty vector store, Gemini errors) the
        function returns safe defaults (empty lists / empty strings) and
        **never raises**.
    """
    pipeline_start = time.perf_counter()

    # ------------------------------------------------------------------
    # Step 1 — Retrieval (Stage 5)
    # ------------------------------------------------------------------
    retrieval_start = time.perf_counter()
    matched_jobs: list[dict[str, Any]] = retrieve_matched_jobs(
        resume_text, top_k=top_k
    )
    retrieval_elapsed = time.perf_counter() - retrieval_start
    logger.info(
        "Retrieval returned %d jobs in %.2f s.", len(matched_jobs), retrieval_elapsed
    )

    # ------------------------------------------------------------------
    # Step 2 — Generation / gap analysis (Stage 6)
    # ------------------------------------------------------------------
    generation_start = time.perf_counter()

    if matched_jobs:
        gap_analysis: dict[str, Any] = generate_gap_analysis(
            resume_text, matched_jobs
        )
    else:
        # No point calling Gemini if there are no jobs to compare against.
        logger.warning(
            "Skipping gap analysis because retrieval returned 0 jobs."
        )
        gap_analysis = {
            "matching_skills": [],
            "missing_skills": [],
            "summary": "",
        }

    generation_elapsed = time.perf_counter() - generation_start
    pipeline_elapsed = time.perf_counter() - pipeline_start

    logger.info(
        "Pipeline complete — retrieval: %.2f s, generation: %.2f s, total: %.2f s.",
        retrieval_elapsed,
        generation_elapsed,
        pipeline_elapsed,
    )

    return {
        "matched_jobs": matched_jobs,
        "gap_analysis": gap_analysis,
    }
