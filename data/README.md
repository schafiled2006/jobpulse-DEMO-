# `data/` — datasets and vector store

Datasets workspace for the data pipeline.

| Path (planned)          | Stage | Contents                                                     |
| ----------------------- | ----- | ------------------------------------------------------------ |
| `data/raw/`             | 1     | Raw scraped/dataset job postings (CSV/JSON/SQLite)           |
| `data/processed/`       | 2–3   | Cleaned + normalized records (`description_raw` kept too)    |
| `data/chroma/`          | 4     | Persistent ChromaDB collection (regenerable by re-embedding) |
| `data/eval/`            | 9     | Labeled resume → expected-jobs test set                      |

Notes:

- Regenerating `data/chroma/` is always possible: re-run the Stage 4 embedding step.
- Never commit resume files uploaded by users, and never commit API keys (use `backend/.env`).
- Keep the embedding model name fixed — the same model must be used at index and query time.
