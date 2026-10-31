"""Retrieval & generation pipeline for Job Pulse.

Stage 5 adds the retrieval logic (ChromaDB + BAAI/bge-m3).
Stage 6 adds the LLM-based gap analysis (Google Gemini).
"""

from app.retrieval.generation import generate_gap_analysis
from app.retrieval.retrieval import retrieve_matched_jobs

__all__ = [
    "generate_gap_analysis",
    "retrieve_matched_jobs",
]
