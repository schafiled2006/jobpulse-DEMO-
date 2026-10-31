
# Job Pulse – Shared Project Context (for any Coding Agent)

## 1. Project Overview

**Name:** Job Pulse (جاب پالس)  
**Goal:** Build a practical full-stack RAG application that helps Iranian job seekers analyze their resume against the real Iranian job market.

The system must:
- Accept a resume (PDF, DOCX, or plain text)
- Retrieve relevant real Iranian job postings using RAG
- Return:
  - Ranked list of matching jobs with match score
  - Matched / missing skills for each job
  - Aggregate market skill-gap summary
- Provide a clean, modern, **Persian-first (RTL)** web interface

This is a **zero-budget MVP** built by two collaborators. Prefer simple, working, maintainable solutions over complex architecture.

## 2. Collaboration Rules

We are two people working on the same GitHub repository (Owner + Collaborator).

### Working Agreement
- We work **stage by stage** and divide tasks based on skills and interest.
- Every stage/task has a clear Owner.
- Code is submitted only through Pull Requests.
- Before merging, the other person should review (or at least be informed).
- Every piece of code must be:
  - Properly **type-hinted** (Python type hints + TypeScript)
  - Reasonably **commented** (especially non-obvious logic, RAG steps, and API contracts)
  - **Testable** – include at least basic tests for important backend logic
- When the AI agent generates code, it must:
  - Add type hints
  - Add clear comments
  - Suggest how the human can quickly test the code
  - Keep changes focused on the current stage only

### How the AI should behave
- You are helping **one of the two collaborators** on a specific stage/task.
- Do not assume you own the whole project.
- Respect existing code and folder structure.
- When requirements are ambiguous, ask clarifying questions before writing a lot of code.
- Prefer small, reviewable changes over large rewrites.

## 3. Locked Tech Stack (Do not change)

### Backend
| Layer              | Choice                                                       | Notes                                      |
| ------------------ | ------------------------------------------------------------ | ------------------------------------------ |
| Framework          | **FastAPI**                                                  | Clean JSON API                             |
| Package Manager    | **uv**                                                       | Preferred Python package manager                 |
| Vector Database    | **ChromaDB** (persistent, local)                             | Simple, free, embedded                     |
| Embedding Model    | `BAAI/bge-m3` (preferred) or `intfloat/multilingual-e5-base` | Strong multilingual + Persian performance  |
| LLM (Generation)   | **Google Gemini API** (2.5 Flash → Flash-Lite fallback)      | Free tier                                  |
| Text Normalization | **Hazm** (for Persian)                                       | Critical for embedding quality             |
| Language           | Python 3.11+                                                 | —                                          |

### Frontend
| Layer     | Choice                           | Notes                         |
| --------- | -------------------------------- | ----------------------------- |
| Framework | **Next.js** (App Router)         | Modern React                  |
| Styling   | **Tailwind CSS** + **shadcn/ui** | Clean, professional, easy RTL |
| Language  | TypeScript                       | Required                      |
| Direction | **RTL-first** + fully Persian UI | All text in Persian           |
| Font      | Vazirmatn (Persian) + Inter      | —                             |
| Theming   | Light + Dark mode                | Required                      |

## 4. High-Level Architecture
- Backend = FastAPI (REST API only) → must be usable independently via Swagger/OpenAPI
- Frontend = Next.js that consumes the backend API
- Folders: keep backend and frontend clearly separated (`/backend` and `/frontend`)
- No tight coupling
- Data pipeline runs offline / periodically; analysis runs live when a user submits a resume

## 5. Core Features (MVP)

### Backend
1. Job data ingestion & embedding into ChromaDB
2. Resume text extraction (PDF / DOCX / plain text)
3. RAG pipeline (retrieve + generate analysis with Gemini)
4. Main analysis endpoint returning structured JSON
5. Basic health & stats endpoints

### Frontend
1. Landing page
2. Resume upload (file + paste text)
3. Loading / analysis state
4. Results page (job cards + aggregate skill-gap summary)
5. Job detail page
6. Light / Dark mode toggle
7. Fully responsive + proper RTL support

## 6. Detailed Development Stages

### Stage 0 – Project Setup
- Create clean monorepo structure (`/backend`, `/frontend`, `/data`, etc.)
- Python project managed with **uv** (not pip/poetry) 
- Empty FastAPI app with `/health` endpoint
- Git setup and basic README
**Success:** Project runs with `uv` and `/health` returns 200.

### Stage 1 – Get the Data
- Scraping data from the Job Vision site using sitemaps
- Load into a DataFrame and filter to a manageable subset 
- Save as local CSV/JSON/SQLite
**Success:** Clean local dataset ready for processing.

### Stage 2 – Clean & Normalize
- Strip HTML, remove duplicates and empty records
- Normalize Persian text with **Hazm** (unify ی/ک, half-spaces, digits, etc.)
- Basic English cleanup
- Keep both `description_raw` and `description_clean`
**Success:** Spot-checking 20 random records shows clean, consistent text.

### Stage 3 – Chunking Decision
- Confirm strategy: **one job ad = one chunk** (job ads are short)
- Only split if unusually long postings are found
**Success:** Token-length check confirms most ads fit the embedding model limit.

### Stage 4 – Embed & Index
- Load `BAAI/bge-m3` (or multilingual-e5-base) via `sentence-transformers`
- Embed all cleaned job ads (use batching)
- Store vectors + metadata in **ChromaDB** (persistent)
**Success:** Test queries in Persian and English return topically relevant job ads.

### Stage 5 – Retrieval Pipeline
- Function: resume text → embed → query ChromaDB (top-k, start with k=10) → return jobs + similarity scores
**Success:** For 5–10 test resumes, top results look relevant to a human.

### Stage 6 – Generation (LLM Gap Analysis)
- Design a strong prompt that receives resume + retrieved jobs
- Ask Gemini for **structured JSON** output:
  - Match score per job
  - Matched skills
  - Missing skills
  - Short explanation
  - Aggregate market skill-gap list
- Add retry/backoff for rate limits
- Instruct the model to only use skills that actually appear in the provided postings
**Success:** Outputs are grounded (can be traced back to real postings) and useful.

### Stage 7 – Backend API
- Wrap retrieval + generation behind FastAPI
- Main endpoint: `POST /analyze` (accepts file or text)
- Proper Pydantic models, error handling, and OpenAPI docs
**Success:** Can call the endpoint with curl/Postman and receive valid JSON.

### Stage 8 – Frontend Foundation + Core Flow
- Next.js + Tailwind + shadcn/ui setup
- RTL + Vazirmatn font + Light/Dark mode
- Pages:
  - Landing
  - Resume Upload (file + paste)
  - Loading state
  - Results (job cards + skill-gap summary)
  - Job Detail
**Success:** Full user flow works end-to-end against the real backend.

### Stage 9 – Evaluation
- Create a small labeled test set (15–20 resume → expected relevant jobs)
- Measure simple recall@k
- Manually check generation quality and grounding
**Success:** You have a basic number to detect regressions.

### Stage 10 – Optional Improvements (Post-MVP)
- Cross-encoder reranker
- Hybrid search (vector + keyword)
- Better data refresh pipeline
- Optional lightweight accounts for history
- Persian-specific embedding experiments

## 7. Important Technical Notes
- Always use the **same embedding model** for indexing and querying.
- Cache Gemini responses during development to save free-tier quota.
- Persian normalization with Hazm is critical — do not skip it.
- Scanned/image-only PDFs will fail text extraction in MVP → show a clear error.
- Analysis can take a few seconds → proper loading states are required.
- Guest-first: core analysis must work without login.

## 8. Coding Standards (Mandatory)
- Type hints everywhere reasonable
- Meaningful comments for complex logic
- Clear naming
- Basic tests for important backend parts
- Graceful error handling
- Small, focused changes per PR

---

### Instruction to the Coding Agent

You are assisting one of the two collaborators on the Job Pulse project.

1. Always respect the locked tech stack and folder structure.
2. Work only on the current stage/task that the human specifies.
3. Generate code that is type-hinted, commented, and easy to test.
4. When you finish a piece of work, briefly tell the human:
   - What you implemented
   - How they can test it
   - What the next logical step is
5. If something is ambiguous or conflicts with existing code, ask before making big changes.
6. Focus on a working, maintainable MVP.

At the start of each session, the human will tell you which stage or task they are working on. Confirm understanding and then proceed.