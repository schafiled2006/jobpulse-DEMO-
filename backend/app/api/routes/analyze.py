"""Endpoint for resume analysis (Stage 7).

Accepts either an uploaded file (PDF/DOCX) or raw text (paste), extracts and
validates the resume text, chains Stage 5 (retrieval) and Stage 6 (generation),
and returns the structured skill-gap analysis.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from starlette.concurrency import run_in_threadpool

from app.core.analyze import analyze_resume
from app.core.limiter import limiter
from app.core.parser import (
    MIN_EXTRACTED_TEXT_LENGTH,
    extract_text_from_file,
)
from app.schemas.analyze import AnalyzeResponse, ErrorDetail

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

MAX_RAW_TEXT_LENGTH: int = 20_000


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="تحلیل رزومه و انطباق با بازار کار (Analyze Resume)",
    description=(
        "یک رزومه (به صورت فایل PDF/DOCX یا متن خام کپی‌شده) را دریافت می‌کند، "
        "آگهی‌های شغلی مرتبط را از پایگاه داده برداری (ChromaDB) استخراج کرده و "
        "با هوش مصنوعی گوگل (Gemini) تحلیل شکاف مهارت‌ها را به صورت خروجی ساختاریافته تولید می‌کند."
    ),
    responses={
        200: {
            "model": AnalyzeResponse,
            "description": "تحلیل با موفقیت انجام شد و آگهی‌های منطبق و مهارت‌ها استخراج گردیدند.",
        },
        400: {
            "model": ErrorDetail,
            "description": "ورودی نامعتبر (نبود فایل یا متن، فایل خالی، متن بسیار کوتاه یا PDF اسکن‌شده).",
        },
        413: {
            "model": ErrorDetail,
            "description": "حجم فایل آپلود شده بیش از ۵ مگابایت است.",
        },
        415: {
            "model": ErrorDetail,
            "description": "فرمت فایل ارسالی پشتیبانی نمی‌شود (فقط PDF و DOCX مجاز است).",
        },
        429: {
            "model": ErrorDetail,
            "description": "تعداد درخواست‌های بیش از حد مجاز (Rate Limit).",
        },
    },
)
@limiter.limit("5/minute")
async def analyze_endpoint(
    request: Request,
    response: Response,
    file: UploadFile | None = File(
        default=None,
        description="فایل رزومه متقاضی (فرمت مجاز: PDF یا DOCX، حداکثر حجم ۵ مگابایت)",
    ),
    text: str | None = Form(
        default=None,
        description="متن خام کپی‌شده رزومه (حداقل ۳۰ و حداکثر ۲۰,۰۰۰ کاراکتر)",
    ),
    top_k: int = Query(
        default=5,
        ge=1,
        le=10,
        description="تعداد آگهی‌های برتر ارسالی به Gemini (پیش‌فرض ۵؛ سقف ۱۰ برای کنترل توکن و تاخیر)",
    ),
) -> dict[str, Any]:
    """Execute the end-to-end resume analysis pipeline.

    1. Validates presence of at least one input (file or text).
    2. Extracts clean text if file is uploaded; or validates string length.
    3. Executes the retrieval (ChromaDB) and generation (Gemini) pipeline in a worker
       threadpool to avoid blocking the asyncio event loop.
    4. Returns structured JSON matching AnalyzeResponse.
    """
    resume_text: str = ""

    # Case 1: File is provided
    if file is not None and file.filename:
        # Pre-validate file metadata
        filename = file.filename
        content_type = file.content_type or ""
        logger.info("Processing uploaded resume file: '%s' (type: %s)", filename, content_type)

        try:
            file_bytes = await file.read()
        except Exception as exc:
            logger.error("Failed to read uploaded file: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="خطا در خواندن فایل ارسالی. لطفاً مجدداً تلاش کنید.",
            ) from exc

        # Extract text using dedicated parser
        resume_text = extract_text_from_file(file_bytes, filename)

    # Case 2: Raw text is provided (when no file is uploaded)
    elif text is not None:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="متن رزومه ارسالی خالی است. لطفاً متن معتبر وارد کنید.",
            )

        if len(cleaned_text) < MIN_EXTRACTED_TEXT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"متن رزومه ارسالی بسیار کوتاه است (حداقل {MIN_EXTRACTED_TEXT_LENGTH} کاراکتر الزامی است).",
            )

        if len(cleaned_text) > MAX_RAW_TEXT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"طول متن رزومه بیش از سقف مجاز ({MAX_RAW_TEXT_LENGTH} کاراکتر) است.",
            )

        resume_text = cleaned_text

    # Case 3: Neither file nor text is provided
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لطفاً یا فایل رزومه (PDF/DOCX) یا متن خام آن را ارسال کنید.",
        )

    # Run the heavy CPU & blocking Gemini retrieval+generation in threadpool.
    # top_k is client-tunable (1..10, default 5) to balance latency/token
    # usage against context quality per the Stage 6 recommendation (3-5).
    logger.info(
        "Starting resume analysis pipeline for %d characters of text (top_k=%d)...",
        len(resume_text),
        top_k,
    )
    result: dict[str, Any] = await run_in_threadpool(
        analyze_resume,
        resume_text=resume_text,
        top_k=top_k,
    )

    return result
