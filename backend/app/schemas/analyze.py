"""Response models for the resume analysis endpoint (Stage 7).

Defines the exact JSON contract returned by ``POST /analyze``.  Both the
FastAPI OpenAPI docs and the Next.js frontend (Stage 8) consume this contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MatchedJob(BaseModel):
    """A single job posting retrieved from ChromaDB matching the candidate's resume."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "job-001",
                "title": "برنامه‌نویس ارشد پایتون (Senior Python Developer)",
                "company": "اسنپ (Snapp)",
                "similarity_score": 0.8542,
                "source_url": "https://jobvision.ir/jobs/snapp-senior-python-001",
                "description_clean": "توسعه‌دهنده ارشد پایتون در اسنپ. مسلط به Django، FastAPI، PostgreSQL، Docker و مفاهیم CI/CD.",
            }
        }
    )

    id: str = Field(
        description="شناسه یکتای آگهی شغلی در سیستم",
        examples=["job-001"],
    )
    title: str = Field(
        description="عنوان موقعیت شغلی",
        examples=["برنامه‌نویس ارشد پایتون"],
    )
    company: str = Field(
        description="نام شرکت یا کارفرما",
        examples=["اسنپ (Snapp)"],
    )
    similarity_score: float = Field(
        description="امتیاز شباهت کسینوسی محاسبه‌شده بین رزومه و آگهی (عددی بین ۰.۰ تا ۱.۰)",
        ge=0.0,
        le=1.0,
        examples=[0.8542],
    )
    source_url: str = Field(
        description="لینک مستقیم مشاهده آگهی در جاب‌ویژن",
        examples=["https://jobvision.ir/jobs/snapp-senior-python-001"],
    )
    description_clean: str = Field(
        description="متن تمیز و پردازش‌شده شرح شغل و نیازمندی‌ها",
        examples=["مسلط به Python، Django، PostgreSQL و Docker."],
    )


class GapAnalysis(BaseModel):
    """Skill-gap analysis produced by Google Gemini based on the resume and retrieved jobs."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "matching_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "missing_skills": ["Django", "Celery", "RabbitMQ", "CI/CD"],
                "summary": "کاندیدا از نظر مهارت‌های پایه بک‌اند با آگهی‌های بازار همخوانی بسیار خوبی دارد، اما برای تطابق با موقعیت‌های ارشد نیاز به تقویت مهارت‌های صف‌بندی (Celery/RabbitMQ) و فرآیندهای CI/CD دارد.",
            }
        }
    )

    matching_skills: list[str] = Field(
        default_factory=list,
        description="لیست مهارت‌هایی که هم در رزومه و هم در آگهی‌های شغلی وجود دارند",
        examples=[["Python", "FastAPI", "PostgreSQL", "Docker"]],
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="لیست مهارت‌های کلیدی خواسته‌شده در آگهی‌ها که در رزومه کاندیدا ذکر نشده‌اند",
        examples=[["Django", "Celery", "RabbitMQ", "CI/CD"]],
    )
    summary: str = Field(
        default="",
        description="خلاصه تحلیلی جامع به زبان فارسی درباره وضعیت رزومه نسبت به بازار کار هدف",
        examples=[
            "کاندیدا تطابق بالایی با موقعیت‌های پایتون دارد اما نیاز به تعمیق مباحث ابزارهای صف و تست خودکار دارد."
        ],
    )


class AnalyzeResponse(BaseModel):
    """The root response object returned by ``POST /analyze``."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "matched_jobs": [
                    {
                        "id": "job-001",
                        "title": "برنامه‌نویس ارشد پایتون",
                        "company": "اسنپ",
                        "similarity_score": 0.8542,
                        "source_url": "https://jobvision.ir/jobs/001",
                        "description_clean": "نیازمند تسلط به پایتون و جنگو",
                    }
                ],
                "gap_analysis": {
                    "matching_skills": ["Python", "FastAPI"],
                    "missing_skills": ["Django", "RabbitMQ"],
                    "summary": "رزومه همخوانی خوبی دارد اما نیازمند تسلط بر جنگو است.",
                },
            }
        }
    )

    matched_jobs: list[MatchedJob] = Field(
        default_factory=list,
        description="لیست آگهی‌های منطبق بازیابی‌شده از دیتابیس برداری به ترتیب نزولی امتیاز شباهت",
    )
    gap_analysis: GapAnalysis = Field(
        default_factory=GapAnalysis,
        description="گزارش تحلیل شکاف مهارتی و خلاصه بازار کار تولید شده توسط LLM",
    )


class ErrorDetail(BaseModel):
    """Standardized error response model."""

    detail: str = Field(
        description="پیام خطای قابل فهم و توصیفی برای کاربر و فرانت‌اند",
        examples=["فرمت فایل آپلود شده پشتیبانی نمی‌شود. لطفاً فایل PDF یا DOCX ارسال کنید."],
    )
