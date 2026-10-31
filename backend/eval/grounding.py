"""Stage 9: skill grounding check (pure logic, no LLM judge)."""
from __future__ import annotations

import re
from typing import Any

_AR_DIGITS = str.maketrans("0123456789", "0123456789")
_FA_FIX = str.maketrans({"ي": "ی", "ك": "ک"})
_AR_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_skill_text(text: str) -> str:
    """نرمال‌سازی سبک: ي/ك عربی، ارقام فارسی، نیم‌فاصله، حروف کوچک."""
    t = (text or "").translate(_AR_FA_DIGITS).translate(_FA_FIX)
    t = t.replace("‌", " ").replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


SKILL_VARIANTS: dict[str, list[str]] = {
    "python": ["پایتون"],
    "django": ["جنگو"],
    "fastapi": ["فست ای پی آی"],
    "postgresql": ["پستگرس"],
    "mysql": ["مای اس کیو ال"],
    "redis": ["ردیس"],
    "celery": ["سلری"],
    "rabbitmq": ["ربیت"],
    "kafka": ["کافکا"],
    "docker": ["داکر"],
    "kubernetes": ["کوبرنتیز"],
    "git": ["گیت"],
    "linux": ["لینوکس"],
    "react": ["ری اکت"],
    "typescript": ["تایپ اسکریپت"],
    "javascript": ["جاوا اسکریپت"],
    "rest api": ["رست"],
    "microservices": ["میکروسرویس"],
    "machine learning": ["یادگیری ماشین"],
    "excel": ["اکسل"],
    "cobol": ["کوبول"],
}


def _grounded(skill: str, blob: str) -> tuple[bool, str]:
    ns = normalize_skill_text(skill)
    if ns and ns in blob:
        return True, "exact"
    for v in SKILL_VARIANTS.get(ns, []):
        if normalize_skill_text(v) in blob:
            return True, "variant"
    toks = [t for t in ns.split() if len(t) > 1]
    if len(toks) > 1 and all(t in blob for t in toks):
        return True, "token"
    return False, "missing"


def check_grounding(skills: list[str], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """هر مهارت در حداقل یکی از آگهی‌ها آمده؟ خروجی نرخ + جزئیات per-skill."""
    blobs = {
        str(j.get("id")): normalize_skill_text(" ".join([
            str(j.get("title", "")), str(j.get("description_clean", "")),
            str(j.get("skills", "")), str(j.get("category", ""))]))
        for j in jobs
    }
    grounded: list[str] = []
    ungrounded: list[str] = []
    details: dict[str, dict[str, Any]] = {}
    for skill in skills:
        covering = [jid for jid, b in blobs.items() if _grounded(skill, b)[0]]
        method = ""
        if covering:
            for jid in covering:
                ok, how = _grounded(skill, blobs[jid])
                if ok:
                    method = how
                    break
            grounded.append(skill)
        else:
            ungrounded.append(skill)
        details[str(skill)] = {"grounded": bool(covering), "method": method, "jobs": covering}
    return {
        "total": len(skills),
        "grounded": grounded,
        "ungrounded": ungrounded,
        "grounding_rate": (len(grounded) / len(skills)) if skills else None,
        "details": details,
    }
