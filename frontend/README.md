# JobPulse Frontend (React + Vite + TypeScript)

Minimalist front-end for the JobPulse backend API. Deliberately built with plain
React on Vite instead of Next.js: no server-side rendering is needed since the
backend is fully decoupled over HTTP, and Vite keeps the dev loop fast and the
dependency tree small.

## Stack

- React 19 + TypeScript (strict)
- Vite 7 (dev server + build)
- No CSS framework, no router, no state library — two components, one API client

## Quick start

```bash
cd frontend
npm install
npm run dev       # serves http://localhost:3000
```

The port matters: the backend's CORS allow-list defaults to
`http://localhost:3000` (see `backend/app/core/config.py`). Keep the frontend on
port 3000 or extend `CORS_ORIGINS` in the backend `.env`.

## Backend requirement

The frontend calls `POST /analyze` on `http://127.0.0.1:8000` (see `src/api.ts`).
Start the backend first:

```bash
cd backend
uv run fastapi dev app/main.py
```

Swagger UI for exploring the contract: <http://127.0.0.1:8000/docs>.

## Features

- Paste raw resume text (min 30 chars, max 20,000) **or** upload a PDF/DOCX file (max 5 MB)
- Choose how many job postings are sent to the LLM (`top_k`, 1–10, default 5)
- Shows the Gemini skill-gap analysis: matching / missing skills + summary
- Lists matched job postings with similarity score, company and link
- Surfaces backend error messages (Persian) directly to the user
- Health-probe banner: warns on load if the backend isn't reachable

Note: the backend rate-limits `/analyze` to 5 requests per minute (HTTP 429);
its Persian message is shown in the UI.

## Build

```bash
npm run build     # type-checks (tsc -b) then bundles to dist/
npm run preview   # serve the production build
```
