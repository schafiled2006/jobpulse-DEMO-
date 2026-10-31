# مستندات استیج ۷ — Backend REST API (`POST /analyze`)

> **مخاطب:** تیم توسعه JobPulse (توسعه‌دهنده بک‌اند و فرانت‌اند)  
> **هدف سند:** تشریح کامل معماری اندپوینت واحد `POST /analyze`، نحوه اعتبارسنجی و استخراج فایل‌ها، اسکیماهای خروجی Pydantic، مدیریت خطاها، Rate Limiting و راهنمای اتصال برای توسعه‌دهنده فرانت‌اند (Next.js).

---

## ۱. خلاصه تغییرات و فایل‌های ایجاد شده

| مسیر فایل | وضعیت | توضیحات |
| :--- | :---: | :--- |
| [`backend/app/schemas/analyze.py`](file:///c:/Users/EA/JobPulse-1/backend/app/schemas/analyze.py) | **جدید** | مدل‌های Pydantic پاسخ (`AnalyzeResponse`, `MatchedJob`, `GapAnalysis`, `ErrorDetail`) با نمونه‌های کامل برای Swagger. |
| [`backend/app/core/parser.py`](file:///c:/Users/EA/JobPulse-1/backend/app/core/parser.py) | **جدید** | ماژول اعتبارسنجی و استخراج متن از فایل‌های PDF (با `pypdf`) و Word (با `python-docx`) همراه با تشخیص PDF اسکن‌شده. |
| [`backend/app/core/limiter.py`](file:///c:/Users/EA/JobPulse-1/backend/app/core/limiter.py) | **جدید** | پیکربندی Rate Limiting سبک مبتنی بر IP کلاینت با استفاده از `slowapi`. |
| [`backend/app/api/routes/analyze.py`](file:///c:/Users/EA/JobPulse-1/backend/app/api/routes/analyze.py) | **جدید** | تعریف اندپوینت `POST /analyze` با دریافت همزمان فایل و متن، اجرای غیرمسدودکننده در Threadpool و تولید مستندات OpenAPI. |
| [`backend/app/main.py`](file:///c:/Users/EA/JobPulse-1/backend/app/main.py) | **ویرایش** | ثبت روت `analyze_router`، اتصال `slowapi` و ExceptionHandler خطای ۴۲۹ با پیام فارسی. |
| [`backend/tests/test_api_analyze.py`](file:///c:/Users/EA/JobPulse-1/backend/tests/test_api_analyze.py) | **جدید** | ۱۱ تست جامع شامل بررسی متون خام، فایل‌های PDF/DOCX، فایل‌های خالی، اسکن‌شده، فرمت‌های غیرمجاز و تست Rate Limit. |
| [`backend/pyproject.toml`](file:///c:/Users/EA/JobPulse-1/backend/pyproject.toml) | **ویرایش** | افزودن وابستگی‌های `pypdf`, `python-docx`, `slowapi`, `python-multipart`. |

---

## ۲. مشخصات و قرارداد اندپوینت (`POST /analyze`)

- **آدرس (URL):** `/analyze`
- **متد:** `POST`
- **نوع محتوا (Content-Type):** `multipart/form-data`
- **محدودیت نرخ (Rate Limit):** حداکثر ۵ درخواست در دقیقه به ازای هر آدرس IP.

### الف) پارامترهای ورودی (Form Fields)

| نام فیلد | نوع | الزامی؟ | محدودیت‌ها | توضیحات |
| :--- | :---: | :---: | :--- | :--- |
| `file` | `UploadFile` | اختیاری* | حداکثر ۵ مگابایت، پسوندهای `.pdf` یا `.docx` | فایل رزومه کاندیدا. |
| `text` | `string` | اختیاری* | حداقل ۳۰ کاراکتر، حداکثر ۲۰,۰۰۰ کاراکتر | متن خام رزومه (کپی/پیست شده). |
| `top_k` | `int` (query param) | اختیاری (پیش‌فرض ۵) | عدد صحیح ۱ تا ۱۰ | تعداد آگهی‌های برتر ارسالی به Gemini (مثال: `/analyze?top_k=3`). |

> ⚠️ **نکته الزامی بودن:** حداقل یکی از فیلدهای `file` یا `text` باید پر باشد؛ در غیر این صورت خطای `400 Bad Request` بازگردانده می‌شود. اگر هر دو ارسال شوند، فایل اولویت دارد.

---

### ب) اسکیما و قرارداد خروجی موفق (`200 OK`)

```json
{
  "matched_jobs": [
    {
      "id": "job-007",
      "title": "برنامه‌نویس جونیور پایتون (Junior Python Developer)",
      "company": "یکتانت (Yektanet)",
      "similarity_score": 0.5503,
      "source_url": "https://jobvision.ir/jobs/yektanet-junior-python-007",
      "description_clean": "برنامه‌نویس جونیور پایتون در یکتانت. همکاری در توسعه وب‌سرویس‌ها..."
    },
    {
      "id": "job-001",
      "title": "برنامه‌نویس ارشد پایتون (Senior Python Developer)",
      "company": "اسنپ (Snapp)",
      "similarity_score": 0.5463,
      "source_url": "https://jobvision.ir/jobs/snapp-senior-python-001",
      "description_clean": "توسعه‌دهنده ارشد پایتون در اسنپ. مسلط به Django و FastAPI..."
    }
  ],
  "gap_analysis": {
    "matching_skills": [
      "Python",
      "Django",
      "PostgreSQL",
      "Docker"
    ],
    "missing_skills": [
      "FastAPI",
      "Redis",
      "Celery",
      "RabbitMQ",
      "CI/CD"
    ],
    "summary": "کاندیدا دارای مهارت‌های پایه و کلیدی بک‌اند از جمله پایتون، جنگو، پستگرس و داکر است..."
  }
}
```

---

### ج) کدهای وضعیت HTTP و مدیریت خطاها (Status Codes)

| کد وضعیت | عنوان خطا | علت رخ دادن | بدنه پاسخ JSON |
| :---: | :--- | :--- | :--- |
| **`200`** | OK | موفقیت در پردازش | شیء `AnalyzeResponse` با ساختار بالا |
| **`400`** | Bad Request | نبود فایل یا متن، فایل ۰ بایتی، متن کمتر از ۳۰ کاراکتر، یا PDF اسکن‌شده (فاقد لایه متنی) | `{"detail": "..."}` با پیام شفاف فارسی |
| **`413`** | Payload Too Large | حجم فایل ارسالی بیش از ۵ مگابایت | `{"detail": "حجم فایل ارسالی بیش از سقف مجاز (۵ مگابایت) است."}` |
| **`415`** | Unsupported Media Type | ارسال فایلی غیر از `.pdf` و `.docx` (مثل `.txt` یا `.png`) | `{"detail": "فرمت فایل پشتیبانی نمی‌شود. لطفاً فایل PDF یا DOCX ارسال کنید."}` |
| **`429`** | Too Many Requests | ارسال بیش از ۵ درخواست در دقیقه از یک IP | `{"detail": "تعداد درخواست‌های شما بیش از سقف مجاز است. لطفاً چند لحظه بعد تلاش کنید."}` |
| **`500`** | Internal Server Error | خطای غیرمنتظره سرور | پیام خطای استاندارد فست‌پی‌آی |

---

## ۳. تصمیمات معماری کلیدی (Architectural Rationale)

1. **مدیریت I/O سنگین و عدم مسدودسازی Event Loop:**
   - فرآیند امبدینگ مدل `bge-m3` روی پردازنده (CPU-bound) و فراخوانی‌های همگام جمینای نباید Event Loop آسنکرون سرور را بلاک کنند.
   - از `run_in_threadpool(analyze_resume, ...)` استفاده شده تا اجرای پایپلاین در worker threadpool جداگانه انجام شود و سایر اندپوینت‌ها (مانند `/health`) بدون تاخیر به کاربران پاسخ دهند.
2. **تشخیص PDF اسکن‌شده (Scanned PDF Detection):**
   - اگر کاربر رزومه تصویری یا اسکن‌شده آپلود کند، متن استخراج‌شده کمتر از ۳۰ کاراکتر خواهد بود. سیستم به‌جای کرش یا فرستادن متن خالی به دیتابیس، خطای شفاف ۴۰۰ برمی‌گرداند تا کاربر متوجه شود باید فایل متنی ارسال کند.
3. **پایداری رابط کاربری (Graceful Degradation):**
   - اگر آگهی مرتبطی پیدا نشود یا خطای موقتی در اتصال اینترنت رخ دهد، سرور کرش نمی‌کند بلکه پاسخ معتبر با لیست خالی برمی‌گرداند تا رابط کاربری فرانت‌اند متلاشی نشود.

---

## ۴. راهنمای اتصال و تست برای همکار فرانت‌اند (Next.js)

### ۱. فراخوانی با متن خام (cURL):
```bash
curl -X POST "http://localhost:8000/analyze?top_k=3" \
  -H "accept: application/json" \
  -F "text=برنامه‌نویس با سابقه پایتون و جنگو و داکر مسلط به پایگاه داده و وب‌سرویس"
```

> پارامتر `top_k` اختیاری است (پیش‌فرض ۵، بازه ۱ تا ۱۰)؛ مقدار خارج بازه خطای `422` می‌دهد. پیش‌فرض ۵ مطابق توصیه استیج ۶ برای کنترل توکن/تاخیر Gemini انتخاب شده است.

### ۲. فراخوانی با آپلود فایل PDF یا Word (cURL):
```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "accept: application/json" \
  -F "file=@/path/to/my_resume.pdf"
```

### ۳. نمونه کد فرانت‌اند در Next.js / TypeScript:
```typescript
const formData = new FormData();
if (selectedFile) {
  formData.append("file", selectedFile);
} else if (pastedText) {
  formData.append("text", pastedText);
}

const response = await fetch("http://localhost:8000/analyze", {
  method: "POST",
  body: formData,
});

if (!response.ok) {
  const errorData = await response.json();
  throw new Error(errorData.detail || "خطا در تحلیل رزومه");
}

const data: AnalyzeResponse = await response.json();
console.log(data.matched_jobs, data.gap_analysis);
```

---

## Update 2026-09-30

- `POST /analyze` حالا کوئری‌پارام اختیاری `top_k` را می‌پذیرد (۱ تا ۱۰، پیش‌فرض ۵) و آن را به `analyze_resume(resume_text, top_k)` پاس می‌دهد؛ خارج بازه → `422`.
- پیش‌فرض `analyze_resume` از ۱۰ به ۵ هم‌تراز شد (توصیه استیج ۶ برای کنترل توکن/تاخیر Gemini).
- تست‌های جدید: `test_top_k_defaults_to_five_and_passes_through`، `test_top_k_query_param_is_forwarded`، `test_top_k_out_of_range_rejected` (مجموع تست‌های `test_api_analyze.py` حالا ۱۴ تست).
