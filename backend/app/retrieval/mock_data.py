"""Stage 5 – Mock job postings dataset for local vector store development.

Contains 10 realistic job postings from major Iranian tech companies (Snapp, Divar,
Digikala, Cafe Bazaar, ArvanCloud, etc.) with mixed Persian and English content.
Each record follows the exact schema expected by the JobPulse pipeline:

- id: Unique job identifier
- title: Job title
- company: Company name
- location: Location / remote status
- date_posted: ISO date or publication date
- description_raw: Raw text description as scraped
- description_clean: Normalized, clean text used for embedding and LLM analysis
- skills_extracted: List of key required skills
- source_url: Link to the posting
- language: Primary language ('fa', 'en', or 'fa-en')
"""

from __future__ import annotations

MOCK_JOBS: list[dict] = [
    {
        "id": "job-001",
        "title": "برنامه‌نویس ارشد پایتون (Senior Python Developer)",
        "company": "اسنپ (Snapp)",
        "location": "تهران (امکان دورکاری)",
        "date_posted": "2026-03-01",
        "description_raw": (
            "ما در تیم فنی اسنپ به دنبال یک توسعه‌دهنده ارشد پایتون هستیم.\n"
            "مسئولیت‌ها:\n"
            "- طراحی و پیاده‌سازی میکروسرویس‌های با مقیاس بالا (High Throughput)\n"
            "- بهینه‌سازی کوئری‌های دیتابیس و طراحی دیتابیس‌های رابطه‌ای\n"
            "- منتورشیپ اعضای جونیور تیم و کدریویو دقیق\n\n"
            "مهارت‌های مورد نیاز:\n"
            "- تسلط کامل به Python و فریم‌ورک‌های Django و FastAPI\n"
            "- تجربه کار عمیق با PostgreSQL و Redis\n"
            "- تسلط به مفاهیم صف و پردازش غیرهمزمان با Celery یا RabbitMQ\n"
            "- آشنایی با Docker و پایپلاین‌های CI/CD\n"
            "- حداقل ۴ سال تجربه کاری مرتبط"
        ),
        "description_clean": (
            "توسعه‌دهنده ارشد پایتون در اسنپ. مسئولیت‌ها شامل طراحی و توسعه "
            "میکروسرویس‌های با مقیاس بالا، بهینه‌سازی دیتابیس و منتورشیپ اعضای تیم است. "
            "نیازمندی‌ها: تسلط کامل به Python، فریم‌ورک‌های Django و FastAPI، پایگاه‌داده "
            "PostgreSQL، کش Redis، صف‌های پیام Celery و RabbitMQ، ابزار Docker و مفاهیم CI/CD."
        ),
        "skills_extracted": [
            "Python",
            "Django",
            "FastAPI",
            "PostgreSQL",
            "Redis",
            "Celery",
            "RabbitMQ",
            "Docker",
            "CI/CD",
            "Microservices",
        ],
        "source_url": "https://jobvision.ir/jobs/snapp-senior-python-001",
        "language": "fa-en",
    },
    {
        "id": "job-002",
        "title": "توسعه‌دهنده بک‌اند FastAPI (Backend Engineer)",
        "company": "دیوار (Divar)",
        "location": "تهران",
        "date_posted": "2026-03-02",
        "description_raw": (
            "دیوار به دنبال یک مهندس بک‌اند با تجربه کار با FastAPI و سیستم‌های توزیع‌شده است.\n"
            "شرح وظایف:\n"
            "- پیاده‌سازی APIهای سریع و با تاخیر پایین بر پایه Asyncio\n"
            "- اتصال و یکپارچه‌سازی سرویس‌ها با استفاده از gRPC و Kafka\n"
            "- مانیتورینگ سرویس‌ها با Prometheus و Grafana\n\n"
            "الزامات شغلی:\n"
            "- تسلط به Python 3.11+ و فریم‌ورک FastAPI\n"
            "- تسلط بر مفاهیم Asynchronous Programming و Coroutines\n"
            "- تجربه کار با Message Brokerها به‌خصوص Apache Kafka\n"
            "- تسلط به پایگاه داده PostgreSQL و معماری میکروسرویس\n"
            "- آشنایی با Docker و Kubernetes"
        ),
        "description_clean": (
            "مهندس بک‌اند FastAPI در دیوار. تمرکز بر پیاده‌سازی سرویس‌های با تاخیر کم "
            "و مقیاس‌پذیر با استفاده از Asyncio و gRPC. نیازمندی‌ها: تسلط بر Python مدرن، "
            "FastAPI، برنامه‌نویسی غیرهمزمان، Apache Kafka، پایگاه داده PostgreSQL، "
            "میکروسرویس، Docker، Kubernetes و مانیتورینگ با Prometheus و Grafana."
        ),
        "skills_extracted": [
            "Python",
            "FastAPI",
            "Asyncio",
            "gRPC",
            "Kafka",
            "PostgreSQL",
            "Docker",
            "Kubernetes",
            "Prometheus",
            "Grafana",
        ],
        "source_url": "https://jobvision.ir/jobs/divar-backend-fastapi-002",
        "language": "fa-en",
    },
    {
        "id": "job-003",
        "title": "Machine Learning Engineer / مهندس یادگیری ماشین",
        "company": "دیجی‌کالا (Digikala)",
        "location": "تهران (امکان دورکاری)",
        "date_posted": "2026-03-03",
        "description_raw": (
            "Digikala is looking for a Machine Learning Engineer to join our Recommendation & Search team.\n"
            "Key Responsibilities:\n"
            "- Research, develop, and deploy NLP and recommendation models.\n"
            "- Fine-tune Transformer architectures (BERT, RoBERTa, LLMs) for Persian e-commerce.\n"
            "- Build and maintain MLOps pipelines for model training and serving.\n\n"
            "Requirements:\n"
            "- Strong programming skills in Python.\n"
            "- In-depth understanding of PyTorch or TensorFlow and Scikit-Learn.\n"
            "- Experience with Hugging Face Transformers and Sentence-Transformers.\n"
            "- Solid knowledge of Vector Databases (ChromaDB, Milvus, or Qdrant).\n"
            "- Experience deploying models using Docker, FastAPI, or Triton Inference Server."
        ),
        "description_clean": (
            "Machine Learning Engineer at Digikala for recommendation and search teams. "
            "Responsibilities include developing and deploying NLP and recommendation models, "
            "fine-tuning transformers, and building MLOps pipelines. Requirements: Python, "
            "PyTorch, Scikit-Learn, Hugging Face Transformers, Sentence-Transformers, "
            "Vector Databases (ChromaDB), Docker, and FastAPI model serving."
        ),
        "skills_extracted": [
            "Python",
            "Machine Learning",
            "PyTorch",
            "NLP",
            "Transformers",
            "Scikit-Learn",
            "ChromaDB",
            "Vector Search",
            "Docker",
            "FastAPI",
        ],
        "source_url": "https://jobvision.ir/jobs/digikala-ml-engineer-003",
        "language": "en",
    },
    {
        "id": "job-004",
        "title": "توسعه‌دهنده فرانت‌اند React و Next.js",
        "company": "کافه‌بازار (Cafe Bazaar)",
        "location": "تهران",
        "date_posted": "2026-03-04",
        "description_raw": (
            "تیم فرانت‌اند کافه‌بازار جهت توسعه محصولات نسل جدید خود از توسعه‌دهندگان مسلط به React دعوت به همکاری می‌نماید.\n"
            "مسئولیت‌ها:\n"
            "- پیاده‌سازی کامپوننت‌های مدرن و ری‌اسپانسف با عملکرد بالا\n"
            "- بهینه‌سازی سئو و رندر سمت سرور با Next.js App Router\n"
            "- رعایت کامل اصول طراحی RTL و استانداردسازی رابط کاربری\n\n"
            "شرایط احراز:\n"
            "- تسلط به JavaScript ES6+ و TypeScript\n"
            "- تسلط کامل بر React.js و فریم‌ورک Next.js (نسخه‌های 14 یا 15)\n"
            "- تسلط بر Tailwind CSS و کتابخانه‌های کامپوننت مانند shadcn/ui\n"
            "- آشنایی با ابزارهای State Management (Redux Toolkit یا Zustand)\n"
            "- آشنایی با Git و روش‌های کار تیمی اسکرام"
        ),
        "description_clean": (
            "توسعه‌دهنده فرانت‌اند React و Next.js در کافه‌بازار. مسئول توسعه کامپوننت‌های "
            "مدرن، بهینه‌سازی SEO با Next.js SSR/SSG و پیاده‌سازی طراحی RTL. نیازمندی‌ها: "
            "TypeScript، JavaScript ES6+، React.js، Next.js App Router، Tailwind CSS، "
            "shadcn/ui، State Management (Zustand/Redux)، REST API و Git."
        ),
        "skills_extracted": [
            "React",
            "Next.js",
            "TypeScript",
            "JavaScript",
            "Tailwind CSS",
            "shadcn/ui",
            "Redux",
            "Zustand",
            "HTML5",
            "CSS3",
            "Git",
        ],
        "source_url": "https://jobvision.ir/jobs/bazaar-frontend-react-004",
        "language": "fa-en",
    },
    {
        "id": "job-005",
        "title": "مهندس دواپس و زیرساخت (DevOps / SRE Engineer)",
        "company": "ابر آروان (ArvanCloud)",
        "location": "تهران (امکان دورکاری کامل)",
        "date_posted": "2026-03-05",
        "description_raw": (
            "ابر آروان در جستجوی یک مهندس SRE/DevOps برای نگهداری و توسعه زیرساخت ابری است.\n"
            "وظایف:\n"
            "- راه‌اندازی و نگهداری کلاسترهای کوبرنتیز در مقیاس وسیع\n"
            "- توسعه پایپلاین‌های اتوماسیون CI/CD با GitLab CI یا GitHub Actions\n"
            "- پیاده‌سازی راهکارهای Infrastructure as Code با Terraform و Ansible\n\n"
            "نیازمندی‌ها:\n"
            "- تسلط عمیق به لینوکس (Debian/Ubuntu/CentOS) و اسکریپت‌نویسی Bash و Python\n"
            "- تجربه حرفه‌ای با Docker و Kubernetes (K8s)\n"
            "- تسلط بر مفاهیم مانیتورینگ، لاگینگ و آلرتینگ (Prometheus, Grafana, ELK)\n"
            "- آشنایی با امنیت شبکه و لودبالانسرهای Nginx و HAProxy"
        ),
        "description_clean": (
            "مهندس دواپس و SRE در ابر آروان. تمرکز بر کلاسترهای Kubernetes، پایپلاین‌های CI/CD، "
            "زیرساخت به عنوان کد با Terraform و اتوماسیون با Ansible. نیازمندی‌ها: لینوکس پیشرفته، "
            "Bash، Python، Docker، Kubernetes، Prometheus، Grafana، ELK Stack، Nginx و شبکه."
        ),
        "skills_extracted": [
            "Linux",
            "Docker",
            "Kubernetes",
            "CI/CD",
            "Terraform",
            "Ansible",
            "Prometheus",
            "Grafana",
            "Bash",
            "Python",
            "GitLab CI",
        ],
        "source_url": "https://jobvision.ir/jobs/arvancloud-devops-005",
        "language": "fa-en",
    },
    {
        "id": "job-006",
        "title": "برنامه‌نویس فول‌استک پایتون و ری‌اکت (Full-Stack Developer)",
        "company": "تپسی (Tapsi)",
        "location": "تهران",
        "date_posted": "2026-03-06",
        "description_raw": (
            "تپسی به دنبال توسعه‌دهنده فول‌استک پرانرژی برای تیم توسعه قابلیت‌های کاربری است.\n"
            "شرح وظایف:\n"
            "- توسعه سرویس‌های سمت سرور با Python و Django/FastAPI\n"
            "- پیاده‌سازی پنل‌ها و صفحات وب اپلیکیشن با React و TypeScript\n"
            "- مشارکت در طراحی دیتابیس و معماری سرویس‌ها\n\n"
            "الزامات:\n"
            "- تسلط هم‌زمان به بک‌اند پایتون و فرانت‌اند React\n"
            "- تجربه کار با PostgreSQL و نوشتن کوئری‌های بهینه\n"
            "- آشنایی با Git، مفاهیم RESTful API و ابزار Docker\n"
            "- توانایی حل مسئله و کار تیمی قوی"
        ),
        "description_clean": (
            "توسعه‌دهنده فول‌استک در تپسی. توسعه توامان بک‌اند پایتون (Django/FastAPI) و "
            "فرانت‌اند React و TypeScript. نیازمندی‌ها: Python، Django، FastAPI، React.js، "
            "TypeScript، پایگاه داده PostgreSQL، REST API، Docker و Git."
        ),
        "skills_extracted": [
            "Python",
            "Django",
            "FastAPI",
            "React",
            "TypeScript",
            "PostgreSQL",
            "REST API",
            "Docker",
            "Git",
        ],
        "source_url": "https://jobvision.ir/jobs/tapsi-fullstack-006",
        "language": "fa-en",
    },
    {
        "id": "job-007",
        "title": "برنامه‌نویس جونیور پایتون (Junior Python Developer)",
        "company": "یکتانت (Yektanet)",
        "location": "تهران",
        "date_posted": "2026-03-07",
        "description_raw": (
            "یکتانت بزرگ‌ترین پلتفرم تبلیغات آنلاین ایران، از علاقه‌مندان به پایتون با انگیزه بالا دعوت به همکاری می‌کند.\n"
            "فرصت یادگیری در کنار مهندسان باتجربه:\n"
            "- کمک در توسعه و تست وب سرویس‌های داخلی\n"
            "- رفع باگ‌ها و بهبود عملکرد کدهای موجود\n\n"
            "مهارت‌های مورد نیاز:\n"
            "- تسلط خوب بر مفاهیم پایه زبان Python و OOP\n"
            "- آشنایی با پایگاه‌های داده رابطه‌ای و مفاهیم اولیه SQL\n"
            "- آشنایی با ابزار کنترل نسخه Git\n"
            "- اشتیاق به یادگیری فریم‌ورک‌های وب مثل Django یا FastAPI\n"
            "- روحیه کارتیمی و توانایی مستندسازی"
        ),
        "description_clean": (
            "برنامه‌نویس جونیور پایتون در یکتانت. همکاری در توسعه وب‌سرویس‌ها و رفع باگ‌ها. "
            "نیازمندی‌ها: درک مناسب از Python، اصول شی‌گرایی (OOP)، مفاهیم پایه‌ای SQL، "
            "آشنایی با Git، علاقه‌مندی به یادگیری Django/FastAPI و اصول Clean Code."
        ),
        "skills_extracted": [
            "Python",
            "OOP",
            "SQL",
            "Git",
            "Django",
            "FastAPI",
            "Clean Code",
        ],
        "source_url": "https://jobvision.ir/jobs/yektanet-junior-python-007",
        "language": "fa-en",
    },
    {
        "id": "job-008",
        "title": "مهندس داده (Data Engineer)",
        "company": "زرین‌پال (ZarinPal)",
        "location": "تهران (امکان دورکاری)",
        "date_posted": "2026-03-08",
        "description_raw": (
            "زرین‌پال جهت تکمیل تیم دیتای خود به دنبال مهندس داده با تجربه در پیاده‌سازی پایپلاین‌های مقیاس‌پذیر است.\n"
            "وظایف:\n"
            "- طراحی و نگهداری خطوط پردازش داده (ETL/ELT)\n"
            "- بهینه‌سازی انبار داده (Data Warehouse) و پایگاه‌های داده تحلیلی\n"
            "- مدیریت جریان داده‌های آنی با Kafka\n\n"
            "الزامات:\n"
            "- تسلط بر Python و نوشتن کدهای کارآمد برای پردازش داده\n"
            "- تسلط پیشرفته بر SQL و طراحی دیتابیس (PostgreSQL, ClickHouse)\n"
            "- تجربه کار با Apache Airflow برای برنامه‌ریزی پایپلاین‌ها\n"
            "- آشنایی با ابزارهای Big Data مانند Apache Spark یا Kafka"
        ),
        "description_clean": (
            "مهندس داده در زرین‌پال. طراحی و پیاده‌سازی خطوط داده ETL/ELT و نگهداری دیتالیک و انبار داده. "
            "نیازمندی‌ها: تسلط بر Python، تسلط عمیق بر SQL، پایگاه‌های داده تحلیلی ClickHouse و PostgreSQL، "
            "ابزار پایپلاینینگ Apache Airflow، جریان داده با Apache Kafka و Apache Spark."
        ),
        "skills_extracted": [
            "Python",
            "SQL",
            "Data Engineering",
            "ETL",
            "Airflow",
            "Kafka",
            "Apache Spark",
            "PostgreSQL",
            "ClickHouse",
            "Data Warehousing",
        ],
        "source_url": "https://jobvision.ir/jobs/zarinpal-data-engineer-008",
        "language": "fa-en",
    },
    {
        "id": "job-009",
        "title": "توسعه‌دهنده موبایل فلاتر (Flutter Developer)",
        "company": "اسنپ‌فود (SnappFood)",
        "location": "تهران",
        "date_posted": "2026-03-09",
        "description_raw": (
            "تیم اپلیکیشن اسنپ‌فود به دنبال یک برنامه‌نویس Flutter با انگیزه جهت ارتقای تجربه کاربری میلیون‌ها کاربر است.\n"
            "مسئولیت‌ها:\n"
            "- پیاده‌سازی صفحات و ویجت‌های نرم و روان در هر دو پلتفرم Android و iOS\n"
            "- اتصال امن و بهینه به REST API و سوکت‌ها\n"
            "- رعایت استانداردهای Clean Architecture و نوشتن تست‌های واحد\n\n"
            "شرایط احراز:\n"
            "- تسلط کامل به فریم‌ورک Flutter و زبان Dart\n"
            "- تجربه با الگوهای مدیریت وضعیت مانند Bloc یا Provider\n"
            "- تجربه کار با Git و آشنایی با فرآیند ریلیز در استورها (کافه‌بازار، مایکت، گوگل پلی)"
        ),
        "description_clean": (
            "توسعه‌دهنده موبایل فلاتر در اسنپ‌فود. پیاده‌سازی رابط کاربری و عملکرد اپلیکیشن در "
            "اندروید و iOS. نیازمندی‌ها: Flutter، Dart، مدیریت وضعیت با Bloc، Clean Architecture، "
            "REST API، Git و آشنایی با تست‌نویسی."
        ),
        "skills_extracted": [
            "Flutter",
            "Dart",
            "Bloc",
            "Mobile Development",
            "Android",
            "iOS",
            "REST API",
            "Git",
            "Clean Architecture",
        ],
        "source_url": "https://jobvision.ir/jobs/snappfood-flutter-009",
        "language": "fa-en",
    },
    {
        "id": "job-010",
        "title": "Senior Go / Golang Developer",
        "company": "ترب (Torob)",
        "location": "تهران (دورکاری)",
        "date_posted": "2026-03-10",
        "description_raw": (
            "Torob is hiring a Senior Golang Backend Engineer to scale high-load search and pricing services.\n"
            "Responsibilities:\n"
            "- Design, develop, and optimize high-concurrency microservices in Go.\n"
            "- Work with distributed caching layers and message brokers.\n"
            "- Ensure system reliability and low-latency responses.\n\n"
            "Requirements:\n"
            "- Proven experience with Go (Golang) and concurrency patterns (goroutines, channels).\n"
            "- Experience with gRPC, Protocol Buffers, and REST APIs.\n"
            "- Deep familiarity with Redis, PostgreSQL, and Elasticsearch.\n"
            "- Experience with Docker, Kubernetes, and CI/CD workflows."
        ),
        "description_clean": (
            "Senior Golang Developer at Torob. Developing high-concurrency search and pricing "
            "microservices. Requirements: Golang (Go), Goroutines, Channels, gRPC, Protobuf, "
            "PostgreSQL, Redis, Elasticsearch, Docker, Kubernetes, and CI/CD."
        ),
        "skills_extracted": [
            "Go",
            "Golang",
            "Microservices",
            "gRPC",
            "Redis",
            "PostgreSQL",
            "Elasticsearch",
            "Docker",
            "Kubernetes",
            "Concurrency",
        ],
        "source_url": "https://jobvision.ir/jobs/torob-golang-010",
        "language": "en",
    },
]
