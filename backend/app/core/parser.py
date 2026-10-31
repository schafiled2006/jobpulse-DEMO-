"""File parser utilities for extracting text from resume documents (PDF / DOCX).

Handles file extraction, validation, corrupt document detection, and detection
of scanned/image-only PDFs with clear, descriptive Persian error messages.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import docx
from fastapi import HTTPException, status
import pypdf
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

# File validation constraints
MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 Megabytes
MIN_EXTRACTED_TEXT_LENGTH: int = 30  # Minimum characters to consider a document non-scanned
ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx"}


def validate_file_metadata(filename: str, file_size: int) -> str:
    """Validate file extension and size before reading contents into memory.

    Parameters
    ----------
    filename:
        The uploaded file's original name.
    file_size:
        Size of the file in bytes.

    Returns
    -------
    str
        The normalized lower-case extension (e.g., '.pdf').

    Raises
    ------
    HTTPException
        415 if extension is unsupported, 413 if size exceeds max, 400 if empty.
    """
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل آپلود شده خالی است (۰ بایت). لطفاً فایل معتبر انتخاب کنید.",
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"حجم فایل ارسالی بیش از سقف مجاز (۵ مگابایت) است.",
        )

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="فرمت فایل پشتیبانی نمی‌شود. لطفاً فایل رزومه را با فرمت PDF یا DOCX ارسال کنید.",
        )

    return ext


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf.

    Parameters
    ----------
    file_bytes:
        Raw binary contents of the PDF file.

    Returns
    -------
    str
        Extracted and stripped text.

    Raises
    ------
    HTTPException
        400 if the PDF is password-protected, corrupt, or contains no selectable text (scanned).
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    except (PdfReadError, Exception) as exc:
        logger.warning("Failed to parse PDF: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل PDF ارسالی خراب یا غیرقابل خواندن است.",
        ) from exc

    if reader.is_encrypted:
        try:
            # Try decrypting with empty password
            decrypt_res = reader.decrypt("")
            if decrypt_res == pypdf.constants.PasswordResult.NOT_DECRYPTED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="فایل PDF دارای رمز عبور است. لطفاً نسخه بدون رمز را ارسال کنید.",
                )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="فایل PDF قفل است و امکان استخراج متن آن وجود ندارد.",
            ) from exc

    pages_text: list[str] = []
    for page_idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        except Exception as exc:
            logger.warning("Error extracting text from page %d: %s", page_idx, exc)

    extracted_text = "\n\n".join(pages_text).strip()

    if len(extracted_text) < MIN_EXTRACTED_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "متنی در فایل PDF یافت نشد. به نظر می‌رسد فایل تصویری یا اسکن‌شده است. "
                "لطفاً نسخه دارای متن را آپلود کنید یا متن رزومه را مستقیماً وارد فرم نمایید."
            ),
        )

    return extracted_text


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from Word DOCX bytes using python-docx.

    Parameters
    ----------
    file_bytes:
        Raw binary contents of the DOCX document.

    Returns
    -------
    str
        Extracted and stripped text from paragraphs and tables.

    Raises
    ------
    HTTPException
        400 if the DOCX file is corrupted or contains insufficient text.
    """
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
    except Exception as exc:
        logger.warning("Failed to parse DOCX: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="فایل DOCX ارسالی خراب یا نامعتبر است.",
        ) from exc

    text_parts: list[str] = []

    # 1. Paragraphs
    for p in doc.paragraphs:
        if p.text.strip():
            text_parts.append(p.text.strip())

    # 2. Tables (resumes often put experience in tables)
    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_text:
                text_parts.append(" | ".join(row_text))

    extracted_text = "\n\n".join(text_parts).strip()

    if len(extracted_text) < MIN_EXTRACTED_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="متن کافی در فایل Word یافت نشد. لطفاً فایل معتبر یا متن رزومه را ارسال کنید.",
        )

    return extracted_text


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Validate and extract text from an uploaded resume file (PDF or DOCX).

    Parameters
    ----------
    file_bytes:
        Binary bytes of the file.
    filename:
        Original filename to determine extension.

    Returns
    -------
    str
        Extracted clean text ready for the RAG pipeline.
    """
    ext = validate_file_metadata(filename, len(file_bytes))
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext == ".docx":
        return extract_text_from_docx(file_bytes)
    else:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="فرمت فایل پشتیبانی نمی‌شود. لطفاً فایل PDF یا DOCX ارسال کنید.",
        )
