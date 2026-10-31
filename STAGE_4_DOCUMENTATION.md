# Stage 4 — Embed & Index

> **مخاطب:** تیم توسعه JobPulse (توسعه‌دهنده + بازبین)  
> **محدوده:** تبدیل آگهی‌های تمیزشده (`data/processed/jobvision_clean.jsonl`) به بردارهای چندبعدی و ذخیره‌سازی در وکتور دیتابیس ChromaDB  
> **استک فنی:** `sentence-transformers` (`BAAI/bge-m3`), `chromadb` (Persistent), `hazm` (Normalizer), `uv`, Python 3.11  
> **آخرین آپدیت:** ۳۰ سپتامبر ۲۰۲۶ — پنجره توکنایزر ۲۰۴۸ (پیش‌فرض CPU) با سقف ۸۱۹۲، آپسرت idempotent، و هم‌ترازی query/index  

---

## ۱. نمای کلی استیج (Overview)

هدف اصلی استیج ۴، دریافت رکوردهای پاک‌سازی‌شده از استیج ۲، تبدیل متن غنی‌شده هر آگهی (`embed_text`) به بردارهای معنایی متراکم (Dense Embeddings)، و ذخیره‌سازی آن‌ها به همراه متادیتای ساختاریافته در پایگاه داده برداری **ChromaDB** است.

### چرا این استیج برای معماری RAG حیاتی است؟
در مرحله بازیابی (استیج ۵)، سیستم باید متن رزومه کاربر را با صدها یا هزاران آگهی شغلی به زبان فارسی مقایسه کند. مقایسه متنی سنتی (کلمه به کلمه) تفاوت‌های نگارشی و مترادف‌های شغلی را تشخیص نمی‌دهد. مدل `BAAI/bge-m3` با تولید بردارهای ۱۰۲۴ بعدی و استفاده از معیار شباهت کسینوسی (Cosine Similarity)، ارتباط معنایی عمیقی بین رزومه و آگهی‌های بازار کار برقرار می‌کند.

---

## ۲. جزئیات پیاده‌سازی و فایل‌ها

### فایل‌های مرتبط با استیج ۴

| مسیر فایل | وضعیت | شرح و مسئولیت |
| :--- | :---: | :--- |
| `backend/ingestion/embed_and_index.py` | تکمیل و آپدیت‌شده (پنجره ۲۰۴۸، CLI ‏`--max-seq-length`، آپسرت) | اسکریپت اصلی پردازش آفلاین، اولویت‌بندی موقعیت‌های فنی (`prioritize_tech`)، ذخیره متادیتای غنی (مهارت‌ها، سابقه، نوع همکاری)، بچ‌بندی و ذخیره در ChromaDB |
| `backend/tests/test_embed_and_index.py` | ۸ تست واحد | تست‌های سریع واحد برای اعتبارسنجی تشخیص شغل فنی، فیلتر رکوردها، بچ‌بندی، اعتبارسنجی متادیتا، اعمال `max_seq_length` و fallback آپسرت به `add` |
| `backend/app/retrieval/retrieval.py` | ارتقایافته | اضافه شدن نرمال‌سازی Hazm برای متن ورودی رزومه، لود آفلاین امن مدل (`local_files_only=True`)، هم‌ترازی پنجره توکنایزر با ایندکس (`embedding_max_seq_length`)، و بازگرداندن متادیتای غنی مهارت‌ها |
| `backend/verify_retrieval.py` | ابزار کمکی | اسکریپت ارزیابی و اعتبارسنجی کیفیت بازیابی معنایی برای رزومه‌های پایتون، هوش مصنوعی، فرانت‌اند و مالی |
| `data/chroma/` | پایگاه داده وکتور | دایرکتوری پایگاه داده محلی ChromaDB (فایل `chroma.sqlite3`) شامل رکوردهای ایندکس‌شده واقعی بازار کار |

---

## ۳. معماری پایپلاین ایندکس‌گذاری

پایپلاین `embed_and_index.py` به ترتیب مراحل زیر را اجرا می‌کند:

1. **بارگذاری و اعتبارسنجی رکوردهای تمیز (`load_cleaned_records`):**
   - خواندن خط‌به‌خط فایل `data/processed/jobvision_clean.jsonl`
   - بررسی فیلتر اعتبار (`is_valid == True` و طول متن کافی)
   - **اولویت‌بندی مشاغل فناوری و آی‌تی (`prioritize_tech=True`):** در حالت ایندکس محدود (مثلاً ۲۰۰ رکورد)، تمامی آگهی‌های حوزه‌های برنامه‌نویسی، هوش مصنوعی، دواپس و شبکه در ابتدای صف قرار می‌گیرند و باقی ظرفیت با نمونه‌های متنوع بازاریابی، مالی، اداری و مهندسی پر می‌شود.
2. **اتصال و مدیریت کالکشن ChromaDB:**
   - اتصال به کلاینت ماندگار (`chromadb.PersistentClient`)
   - تنظیم کالکشن با متریک فاصله کسینوسی: `{"hnsw:space": "cosine"}`
   - در صورت بازسازی کامل (`clean_rebuild=True`)، کالکشن قبلی حذف و مجدداً ایجاد می‌شود.
3. **بارگذاری مدل امبدینگ (Offline-First):**
   - لود مدل `BAAI/bge-m3` با پارامتر `local_files_only=True` از کش محلی هاب هاگینگ‌فیس (لود سریع در کمتر از ۲ ثانیه بدون معطلی و خطای شبکه)
   - تنظیم `max_seq_length = 2048` (پیش‌فرض CPU؛ سقف 8192 طبق استیج ۳، قابل تنظیم با `--max-seq-length` و `EMBEDDING_MAX_SEQ_LENGTH`) جهت بهینه‌سازی سرعت محاسبات روی CPU و جلوگیری از اسپایک مصرف رم.
4. **پردازش دسته‌ای (Batch Processing):**
   - رکوردهای متنی در دسته‌های ۳۲تایی (`batch_size=32`) پردازش می‌شوند.
   - برای هر آگهی، فیلد `embed_text` با پارامتر `normalize_embeddings=True` تبدیل به بردار ۱۰۲۴ بعدی می‌شود.
5. **ذخیره در ChromaDB به همراه متادیتای غنی:**
   - `ids`: شناسه یکتای آگهی (`id`)
   - `embeddings`: وکتورهای متراکم ۱۰۲۴ بعدی
   - `documents`: شرح تمیز شغل (`description_clean`)
   - `metadatas`:
     ```python
     {
         "title": title[:500],
         "company": company[:500],
         "location": location[:500],
         "category": category[:500],
         "source_url": source_url[:500],
         "description_clean": description_clean[:3000],
         "skills": skills_str[:500],
         "employment_type": employment_type[:100],
         "experience_level": experience_level[:100],
     }
     ```

---

## ۴. نحوه استفاده و اجرای اسکریپت (CLI Usage)

تمامی دستورات با مدیریت پکیج `uv` از داخل پوشه `backend/` اجرا می‌شوند:

```bash
# ۱. ایندکس کردن ۲۰۰ رکورد برتر با اولویت موقعیت‌های تخصصی فناوری (پیشنهادی برای توسعه لوکال، ~۲.۵ دقیقه):
uv run python -m ingestion.embed_and_index --limit 200

# ۲. ایندکس کردن تمام ۱۹۸۷ آگهی معتبر بازار کار ایران:
uv run python -m ingestion.embed_and_index --all

# ۳. ایندکس کردن ۲۰۰ رکورد بر اساس ترتیب اولیه فایل بدون اولویت‌بندی فنی:
uv run python -m ingestion.embed_and_index --limit 200 --no-tech-priority

# ۴. اعتبارسنجی کیفیت بازیابی و مشاهده آگهی‌های تطابق‌یافته در ترمینال:
uv run python verify_retrieval.py
```

---

## ۵. نتایج واقعی بازیابی روی داده‌های بازار کار (Verification Results)

اجرای کوئری‌های تستی روی پایگاه داده ChromaDB با ۲۰۰ آگهی واقعی جاب‌ویژن نتایج زیر را به همراه داشت:

| عنوان کوئری تستی | بهترین موقعیت بازیابی‌شده | شرکت | مهارت‌های منطبق | امتیاز شباهت |
| :--- | :--- | :--- | :--- | :---: |
| **برنامه نویس پایتون و جنگو** | Software Engineer (Python) | فیوتریکس | Python, Django, PostgreSQL, Docker, Git | **۰.۵۹۶۹** |
| **Machine Learning & NLP** | Software Engineer (Python & AI) | فیوتریکس | Python, Django, PostgreSQL, Linux | **۰.۶۲۰۰** |
| **توسعه‌دهنده React و Next.js** | برنامه‌نویس فرانت اند | پرشین سیستم | Next.js, React, TypeScript, REST API | **۰.۶۳۲۶** |
| **حسابداری و مالی با اکسل** | کارشناس مالی و حسابداری | آفتاب خودرو | Excel, همکاران سیستم, راهکاران | **۰.۷۳۳۱** |

---

## ۶. تست‌های خودکار (Automated Tests)

تست‌های واحد استیج ۴ در فایل `tests/test_embed_and_index.py` به صورت ۱۰۰٪ Mocked و سریع اجرا می‌شوند:

```bash
uv run pytest tests/test_embed_and_index.py -v
```

### موارد تست‌شده:
1. `test_is_tech_job_detection`: شناسایی درست کلمات کلیدی فناوری در عنوان، دسته‌بندی یا مهارت‌ها.
2. `test_load_cleaned_records_filters_invalid_and_applies_limit`: نادیده گرفتن رکوردهای نامعتبر و اعمال درست محدودیت `--limit`.
3. `test_load_cleaned_records_prioritize_tech`: قرارگیری مشاغل فنی در صدر لیست هنگام فعال بودن اولویت‌بندی.
4. `test_load_cleaned_records_missing_file`: پرتاب خطای صریح در صورت نبودن فایل دیتا.
5. `test_index_jobs_batches_and_stores_in_chromadb`: تست محاسبات بچ‌بندی، ذخیره متادیتا (`skills`, `experience_level`) و فراخوانی `clean_rebuild`.
6. `test_index_jobs_empty_list`: تست رفتار امن تابع با ورودی خالی.
7. `test_index_jobs_applies_max_seq_length`: اعمال `max_seq_length` روی مدل امبدینگ.
8. `test_index_jobs_upsert_fallback_to_add`: ذخیره با `upsert` و fallback به `add` روی ChromaDB قدیمی.

---

## Update 2026-09-30

- پنجره پیش‌فرض توکنایزر 512 به 2048 ارتقا یافت (CLI ‏`--max-seq-length`، متغیر `EMBEDDING_MAX_SEQ_LENGTH`)؛ سقف سخت 8192 طبق تصمیم استیج ۳ (one ad = one chunk) حفظ شده است.
- `index_jobs` حالا با `upsert()` می‌نویسد (idempotent؛ مناسب `--no-clean-rebuild`) و روی بیلدهای قدیمی ChromaDB به `add()` برمی‌گردد.
- سمت کوئری (`app/retrieval/retrieval.py`) همان پنجره را از `settings.embedding_max_seq_length` می‌گیرد تا truncate ایندکس/کوئری یکسان باشد.
- نکته بازسازی: دیتابیس ChromaDB ساخته‌شده با پنجره 512 باید clean-rebuild شود (`--all`) تا پنجره جدید اعمال شود.
