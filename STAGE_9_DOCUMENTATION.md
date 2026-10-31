# مستندات استیج ۹ — Evaluation (ارزیابی بازیابی و گراندینگ)

> **مخاطب:** تیم توسعه JobPulse (توسعه‌دهنده و بازبین)
> **هدف سند:** تشریح ماژول ارزیابی آفلاین پروژه: مجموعه طلایی (Golden Set)، معیارهای `recall@k` و Grounding، نحوه اجرای CLI، خط پایه فعلی و تست‌ها.
> **استک فنی:** Python 3.11 (کتابخانه استاندارد) + `pytest` — **بدون هیچ وابستگی جدیدی** (حتی PyYAML هم اضافه نشده؛ لودر YAML مخصوص همین فایل نوشته شده).
> **آخرین آپدیت:** ۲ اکتبر ۲۰۲۶ — تکمیل runner، CLI، گزارش‌نویس و ۱۶ نمونه Golden Set.

---

## ۱. فایل‌های ایجاد/ویرایش‌شده

| مسیر فایل | وضعیت | توضیحات |
| :--- | :---: | :--- |
| `backend/eval/__init__.py` | **جدید** | re-export توابع عمومی: `load_golden_set`، `recall_at_k`، `mean_recall`، `check_grounding`. |
| `backend/eval/metrics.py` | **جدید** | لودر Golden Set با پارسر YAML سبک (فقط ساختار همین فایل، بدون pyyaml). |
| `backend/eval/recall.py` | **جدید** | محاسبه `recall@k` (کل‌های `1,3,5,10`) و میانگین آن؛ نمونه‌های بدون `expected` حذف می‌شوند (NaN). |
| `backend/eval/grounding.py` | **جدید** | بررسی گراندینگ مهارت‌ها با سه روش `exact` / `variant` (معادل فارسی) / `token` — بدون LLM. |
| `backend/eval/report.py` | **ویرایش** | حلقه ارزیابی؛ DI برای تست‌پذیری، مقاومت در برابر خطای بازیابی/Generation و عدم کش نتایج خالی. |
| `backend/eval/writer.py` | **ویرایش** | گزارش JSON سخت‌گیرانه (`NaN/Infinity → null`) + گزارش Markdown. |
| `backend/eval/run_eval.py` | **تکمیل شد** | پارسر CLI، کش پاسخ Gemini، تابع `main()` و خلاصه آماری در stdout. |
| `backend/eval/cli.py` | **تکمیل شد** | نقطه ورود `python -m eval.cli`. |
| `backend/tests/test_eval.py` | **جدید** | ۱۷ تست سریع (موک‌کردن بازیابی/Generation — بدون مدل و بدون Gemini). |
| `data/eval/golden_set.yaml` | **ویرایش** | ۱۲ → **۱۶ نمونه** (وردپرس، گرافیک، سئو، منابع انسانی) مطابق بازه ۱۵–۲۰ در `PROJECT_CONTEXT.md`. |
| `.gitignore` | **ویرایش** | نادیده‌گرفتن `data/eval/reports/` (خروجی قابل‌بازتولید). |

---

## ۲. معماری و جریان اجرا

```
golden_set.yaml ─▶ load_golden_set() ─▶ run_evaluation()
                                            │
                 ┌──────────────────────────┤
                 ▼                          ▼  (فقط mode=full)
   retrieve_matched_jobs(resume, top_k)   generate_gap_analysis()
                 │                        │  └─ کش: backend/eval/.cache/
                 ▼                        ▼
        recall@k per sample       check_grounding(skills, jobs)
                 │                        │
                 └────────────┬───────────┘
                              ▼
              write_report() → eval_<stamp>_<mode>.json + .md
                              ▼
              خلاصه آماری در stdout (mean recall + مسیر گزارش)
```

- `report.run_evaluation` با **تزریق ماژول** (`recall_mod`, `cache_mod`, `grounding_mod`) نوشته شده تا در تست‌ها بدون Gemini قابل‌اجرا باشد.
- خطای یک نمونه (مثلاً ChromaDB در دسترس نیست) کل اجرا را از بین نمی‌برد؛ نمونه به‌صورت hit صفر ثبت می‌شود.

---

## ۳. مجموعه طلایی (`data/eval/golden_set.yaml`)

- **۱۶ نمونه رزومه** (۱۴ نمونه با `expected_job_ids` غیرخالی + ۲ نمونه edge بدون انتظار match).
- دامنه‌ها: backend، frontend، ml-ai، data، devops، network، finance، cms، design، marketing، hr، edge.
- قانون برچسب‌گذاری (دستی، مستقل از خروجی سیستم): آگهی expected است که **هم‌حوزه و هم‌سطح** رزومه باشد؛ آگهی نامرتبط حتی با امتیاز بالا expected نیست.
- همه ایدی‌ها با `data/processed/jobvision_clean.jsonl` (`is_valid=True`) راستی‌آزمایی می‌شوند؛ تست `test_golden_ids_exist_in_dataset` این تطابق را در هر اجرا نگه می‌دارد.
- ترتیب فیلدهای هر نمونه: `id` ← `lang/domain/level` ← `resume_text` ← `expected_job_ids` ← `notes` (پارسر فایل‌های چندخطی `>-` را به همین ترتیب می‌خواند).

---

## ۴. معیارها

| معیار | تعریف |
| :--- | :--- |
| `recall@k` | نسبت `expected_job_ids` که در k تای اول بازیابی دیده شده‌اند؛ اگر `expected` خالی باشد `NaN` است و در میانگین حذف می‌شود. |
| `grounding_rate` | نسبت مهارت‌های گزارش Gemini که در **حداقل یکی** از آگهی‌های بازیابی‌شده واقعاً آمده‌اند (تشخیص exact/variant/token — بدون LLM قاضی). |

---

## ۵. نحوه اجرا

```bash
cd backend

# ۱) ارزیابی بازیابی — آفلاین، بدون سهمیه Gemini (پیش‌فرض)
uv run python -m eval.cli --mode retrieval

# ۲) ارزیابی کامل — افزودن Gap Analysis و Grounding (نیازمند GEMINI_API_KEY)
uv run python -m eval.cli --mode full --top-k 5
```

| پرایتمتر | پیش‌فرض | توضیح |
| :--- | :---: | :--- |
| `--mode` | `retrieval` | `retrieval` = فقط recall@k؛ `full` = + Gemini و گراندینگ. |
| `--golden` | `data/eval/golden_set.yaml` | مسیر مجموعه طلایی. |
| `--top-k` | `10` | عمق بازیابی (تعداد آگهی‌های fetch شده برای هر رزومه). |
| `--limit` | `0` | فقط N نمونه اول (۰ = همه). |
| `--no-cache` | خاموش | نادیده‌گرفتن کش پاسخ Gemini. |
| `--out` | `data/eval/reports/` | دایرکتوری خروجی گزارش‌ها. |

- **کش Gemini:** `backend/eval/.cache/` با کلید `sha256(resume + job_ids)`؛ نتایج **خالی هرگز کش نمی‌شوند** (جلوگیری از مسموم‌شدن کش با خطای نبود کلید).
- **کد خروج:** `0` = موفق؛ `1` = ورودی نامعتبر / فایل Golden خالی یا ناموجود.
- خروجی: `data/eval/reports/eval_<stamp>_<mode>.json` + `.md` (در git نادیده گرفته می‌شوند).

---

## ۶. خط پایه (Baseline) — ۲۰۲۶-۱۰-۰۲

اجرای واقعی `--mode retrieval --top-k 10` روی ۱۶ نمونه (CPU، ۵.۱ ثانیه):

| معیار | مقدار |
| :--- | :---: |
| recall@1 | **۰.۱۱۳** |
| recall@3 | **۰.۱۱۳** |
| recall@5 | **۰.۱۱۳** |
| recall@10 | **۰.۱۳۷** |

> ⚠️ **تفسیر:** عدد پایین است و عمدتاً آگهی‌های expected در ۱۰ تای اول نیستند (مثلاً نمونه‌های backend هیچ‌کدام از ۳ ایدی مورد انتظار را نمی‌بینند). محتمل‌ترین علت: ایندکس محلی هنوز با پنجره توکنایزر قدیمی ساخته شده و **rebuild با پنجره جدید استیج ۴ (۲۰۴۸/۸۱۹۲) انجام نشده است.** هدف استیج ۹ «عدد پایه برای تشخیص regression» است؛ پس از rebuild ایندکس، این اجرا را تکرار و با همین جدول مقایسه کنید.

---

## ۷. تست‌ها

```bash
cd backend
uv run pytest tests/test_eval.py -v   # 17 تست — همگی سریع و آفلاین
```

پوشش: لودر Golden Set (فایل واقعی + فایل موقت + تطابق ایدی‌ها با دیتاست)، `recall@k` و میانگین (شامل NaN)، نرمال‌سازی مهارت‌ها و سه روش گراندینگ، حلقه ارزیابی retrieval/full (موک + اعتبارسنجی کش Gemini)، خروجی strict JSON و Markdown گزارش، CLI (`main`) شامل مسیرهای خطا و پرچم `--no-cache`.

---

## ۸. ملاحظات و محدودیت‌ها

1. حالت `full` بدون `GEMINI_API_KEY` هم اجرا می‌شود ولی `matching/missing` خالی خواهد بود و `grounding_rate = n/a` (هشدار در stderr چاپ می‌شود).
2. Golden Set باید همراه رفرش دیتاست (استیج ۱/۲) به‌روز شود؛ تست تطابق ایدی‌ها، شکست برچسب‌ها را زود نشان می‌دهد.
3. گزارش‌ها جزو خروجی‌های قابل‌بازتولیدند و کامیت نمی‌شوند؛ عدد خط پایه در همین سند نگهداری می‌شود.
4. `STAGES_STATUS_REPORT.md` یک گزارش تاریخ‌دار (۲۵ سپتامبر) است و عمداً ویرایش نشد.