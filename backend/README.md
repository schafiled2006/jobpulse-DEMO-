# Job Pulse — Backend (FastAPI)

REST API for Job Pulse. It is usable on its own through Swagger UI / OpenAPI, with no
dependency on the frontend.

**Stack (locked):** FastAPI · `uv` · ChromaDB · `BAAI/bge-m3` · Google Gemini · Hazm · Python 3.11+

## Quick start

```bash
cd backend
uv sync                 # creates .venv and installs dependencies (+ dev tools)
uv run fastapi dev app/main.py
```

Then open:

- Health check → <http://127.0.0.1:8000/health> (expects `200` and `{"status": "ok", ...}`)
- Swagger UI → <http://127.0.0.1:8000/docs>
- ReDoc → <http://127.0.0.1:8000/redoc>

Quick check from a second terminal:

```bash
curl -s http://127.0.0.1:8000/health
```

## Tests

```bash
cd backend
uv run pytest           # add -q for a compact report
```

## Configuration

Settings are typed in `app/core/config.py` and read from environment variables or a local
`.env` file. Copy the template to get started — nothing is required for Stage 0:

```bash
cd backend
cp .env.example .env
```

`GEMINI_API_KEY` (Stage 6), `EMBEDDING_MODEL_NAME` and `CHROMA_PERSIST_DIR` (Stage 4) are
already reserved there.

## Layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI factory + lifespan + router wiring
│   ├── api/routes/             # one module per feature (health.py, later analyze.py)
│   ├── core/config.py          # typed settings
│   └── schemas/                # Pydantic request/response contracts
├── tests/                      # pytest suite
├── pyproject.toml              # uv project (+ dev group, pytest config)
└── .env.example                # configuration template
```

Planned additions: `app/services/` for ingestion, normalization, embedding and retrieval
(Stages 1–5), and `app/services/generation.py` for the Gemini gap analysis (Stage 6).

## Optional: run as a `uv` workspace

This project is intentionally self-contained (its own `.venv` and `uv.lock`). If you would
rather share one virtual environment and lockfile across the monorepo, add this to a root
`pyproject.toml` and re-lock:

```toml
[tool.uv.workspace]
members = ["backend"]
```

Then `rm -rf backend/.venv backend/uv.lock && uv sync` at the repository root.
