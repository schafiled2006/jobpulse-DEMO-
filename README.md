# JobPulse

An AI-powered platform that helps Iranian job seekers analyze their resume against the real Iranian job market using Retrieval-Augmented Generation: upload a resume, retrieve relevant job postings, and get a skill-gap analysis with market-demand insights.

This is a zero-budget MVP built by two collaborators. See [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) for the shared context, locked tech stack, and stage plan.

## Repository layout

```
JobPulse/
├── backend/            # FastAPI service (uv project) — usable standalone via Swagger
│   ├── app/            # API code: main.py, api/routes/, core/config.py, schemas/
│   ├── tests/          # pytest suite
│   └── README.md       # how to run and test the backend
├── data/               # local datasets + ChromaDB persistence (git-ignored)
├── frontend/           # Next.js app (Stage 8)
├── PROJECT_CONTEXT.md  # shared project context for collaborators and AI agents
└── README.md
```

Backend and frontend are intentionally decoupled: the frontend only talks to the backend
over HTTP, so the API can be explored and tested on its own.

## Quick start (backend)

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

- Health check: <http://127.0.0.1:8000/health>
- API docs (Swagger UI): <http://127.0.0.1:8000/docs>

```bash
curl -s http://127.0.0.1:8000/health     # -> {"status":"ok","service":"jobpulse-backend",...}
cd backend && uv run pytest              # run the test suite
```

Details, configuration and the folder map: [`backend/README.md`](./backend/README.md).

## Contributing

- Work stage by stage; each stage has a clear owner.
- Open a Pull Request for every change and ask the other collaborator to review.
- Every change must be type-hinted, commented where non-obvious, and covered by basic tests.

