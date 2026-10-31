"""Stage 6 – LLM-based skill-gap analysis using Google Gemini API.

This module provides :func:`generate_gap_analysis`, which sends a candidate's
resume together with a set of retrieved job postings to Google Gemini and returns
a structured skill-gap report.

Design decisions
~~~~~~~~~~~~~~~~
* **Model cascade** – tries ``gemini-2.5-flash`` first; on rate-limit (429)
  errors falls back to ``gemini-2.5-flash-lite`` (lighter, higher quota).
* **Structured output** – uses the SDK's ``response_format`` parameter with a
  JSON schema so the model is constrained to produce valid JSON matching our
  contract.  A belt-and-suspenders prompt instruction also asks for raw JSON.
* **Retry with exponential back-off** – up to 3 attempts per model on 429.
* **Graceful degradation** – on unrecoverable errors the function returns an
  empty-but-valid dict instead of crashing, so downstream code can always rely
  on the schema.

Usage::

    from app.retrieval.generation import generate_gap_analysis

    result = generate_gap_analysis(resume_text, matched_jobs)
    # result == {"matching_skills": [...], "missing_skills": [...], "summary": "..."}
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env so GEMINI_API_KEY is available even when running outside FastAPI
# (e.g. from tests or standalone scripts).  The .env file is expected in the
# backend/ directory (the same place pydantic-settings looks).
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIMARY_MODEL: str = "gemini-3.5-flash-lite"
_FALLBACK_MODEL: str = "gemini-3.1-flash-lite"

_MAX_RETRIES: int = 3
_INITIAL_BACKOFF_SECONDS: float = 2.0

# Safe empty result returned when generation or parsing fails, so the caller
# always receives the expected schema.
_EMPTY_RESULT: dict[str, Any] = {
    "matching_skills": [],
    "missing_skills": [],
    "summary": "",
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = """\
You are an expert career advisor and skills analyst.  You will receive:
1. A candidate's resume text.
2. The full text of several job postings that were retrieved as potential matches.

Your task is to perform a **skill-gap analysis**:

• **matching_skills** – skills, technologies, or qualifications that appear
  BOTH in the resume AND in at least one of the provided job postings.
• **missing_skills** – skills, technologies, or qualifications that are
  required or mentioned in the job postings but are NOT present in the resume.
• **summary** – a concise paragraph (2–4 sentences) in Persian summarising the
  candidate's overall fit and the most critical gaps they should address.

STRICT RULES – you MUST follow all of them:
1. Only list skills that are *explicitly* mentioned in the provided job
   postings.  Do NOT invent or hallucinate skills that do not appear in the
   given texts.
2. The resume and job postings may be in Persian (فارسی), English, or a mix.
   Keep skill names in the language they appear in the source texts (e.g. if a
   posting says "React" keep "React"; if it says "مدیریت پروژه" keep
   "مدیریت پروژه").
3. Write the summary in Persian.
4. Output ONLY raw JSON – no markdown fences, no extra text, no explanation
   before or after the JSON object.
"""

# ---------------------------------------------------------------------------
# JSON response schema (for the SDK's structured-output constraint)
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "matching_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Skills present in both the resume and at least one job posting."
            ),
        },
        "missing_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Skills required by job postings but absent from the resume."
            ),
        },
        "summary": {
            "type": "string",
            "description": (
                "A concise Persian paragraph summarising fit and gaps."
            ),
        },
    },
    "required": ["matching_skills", "missing_skills", "summary"],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_user_prompt(resume_text: str, matched_jobs: list[dict]) -> str:
    """Assemble the user-side prompt containing resume + job texts."""

    jobs_parts: list[str] = []
    for idx, job in enumerate(matched_jobs, start=1):
        title = job.get("title", "بدون عنوان")
        company = job.get("company", "نامشخص")
        description = job.get("description_clean", "")
        jobs_parts.append(
            f"--- آگهی {idx} ---\n"
            f"عنوان شغل: {title}\n"
            f"شرکت: {company}\n"
            f"متن آگهی:\n{description}\n"
        )

    jobs_block = "\n".join(jobs_parts)

    return (
        f"=== رزومه کاندیدا ===\n{resume_text}\n\n"
        f"=== آگهی‌های شغلی بازیابی‌شده ===\n{jobs_block}"
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```json … ```) if the model wraps them."""

    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    # Drop the opening ``` or ```json line.
    if lines[0].startswith("```"):
        lines = lines[1:]
    # Drop the closing ``` line.
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Heuristic check whether *exc* represents an HTTP 429 / RESOURCE_EXHAUSTED.

    The ``google-genai`` SDK may surface rate-limit errors as different exception
    types across versions, so we also inspect the string representation as a
    fallback.
    """

    # Some SDK versions expose a numeric status_code attribute.
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code == 429:
        return True

    # Fallback: check the string representation for common markers.
    exc_lower = str(exc).lower()
    return (
        "429" in exc_lower
        or "rate limit" in exc_lower
        or "resource_exhausted" in exc_lower
        or "resource exhausted" in exc_lower
    )


def _call_gemini(
    client: genai.Client,
    model: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Send a single request to Gemini and return the parsed JSON dict.

    Raises on HTTP / network / JSON errors so the caller can decide whether to
    retry or fall back.
    """

    interaction = client.interactions.create(
        model=model,
        input=user_prompt,
        system_instruction=_SYSTEM_PROMPT,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": _RESPONSE_SCHEMA,
        },
        # Don't store interactions — we don't need server-side history for
        # one-shot analysis calls.
        store=False,
    )

    raw_text: str = interaction.output_text or ""
    raw_text = _strip_markdown_fences(raw_text)

    return json.loads(raw_text)  # may raise json.JSONDecodeError


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_gap_analysis(
    resume_text: str,
    matched_jobs: list[dict],
) -> dict[str, Any]:
    """Analyse a resume against retrieved job postings and return a skill-gap report.

    Parameters
    ----------
    resume_text:
        Raw text extracted from the candidate's resume.
    matched_jobs:
        List of dicts, each expected to contain at least:
        ``id``, ``title``, ``company``, ``similarity_score``, ``source_url``,
        and ``description_clean``.

    Returns
    -------
    dict
        ``{"matching_skills": [...], "missing_skills": [...], "summary": "..."}``

        On unrecoverable errors an empty-but-valid dict is returned (never
        raises), so downstream code can always rely on the schema.
    """

    # --- Resolve API key -------------------------------------------------
    api_key: str | None = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error(
            "GEMINI_API_KEY is not set in environment variables. "
            "Cannot call Gemini API — returning empty gap analysis."
        )
        return dict(_EMPTY_RESULT)

    client_args: dict[str, Any] = {"trust_env": False}
    gemini_proxy = os.environ.get("GEMINI_PROXY")
    if gemini_proxy:
        client_args["proxy"] = gemini_proxy

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(client_args=client_args),
    )
    user_prompt = _build_user_prompt(resume_text, matched_jobs)

    # --- Try primary model, then fallback on rate-limit ------------------
    models_to_try: list[str] = [_PRIMARY_MODEL, _FALLBACK_MODEL]

    for model in models_to_try:
        backoff = _INITIAL_BACKOFF_SECONDS

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = _call_gemini(client, model, user_prompt)

                # Validate / normalise the result to guarantee the contract.
                validated: dict[str, Any] = {
                    "matching_skills": list(result.get("matching_skills", [])),
                    "missing_skills": list(result.get("missing_skills", [])),
                    "summary": str(result.get("summary", "")),
                }
                logger.info(
                    "Gap analysis succeeded (model=%s, attempt=%d).",
                    model,
                    attempt,
                )
                return validated

            except json.JSONDecodeError as exc:
                # JSON parse failure is unlikely with structured output but
                # we handle it.  No point retrying the same model – break to
                # try the fallback.
                logger.warning(
                    "JSON parse error with model=%s on attempt %d: %s",
                    model,
                    attempt,
                    exc,
                )
                break

            except Exception as exc:  # noqa: BLE001
                if _is_rate_limit_error(exc):
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            "Rate limit (429) with model=%s, attempt %d/%d. "
                            "Retrying in %.1f s …",
                            model,
                            attempt,
                            _MAX_RETRIES,
                            backoff,
                        )
                        time.sleep(backoff)
                        backoff *= 2
                        continue

                    # Exhausted retries for this model – break to fallback.
                    logger.warning(
                        "Rate limit exhausted for model=%s after %d attempts. "
                        "Trying fallback model …",
                        model,
                        _MAX_RETRIES,
                    )
                    break

                # Non-rate-limit error – log and break to fallback.
                logger.error(
                    "Unexpected Gemini error with model=%s on attempt %d: %s",
                    model,
                    attempt,
                    exc,
                )
                break

    # All models / retries exhausted — return safe empty result.
    logger.error(
        "All Gemini models and retries exhausted. Returning empty gap analysis."
    )
    return dict(_EMPTY_RESULT)
