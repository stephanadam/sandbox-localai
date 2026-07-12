# sandbox-localai — Legal Analyst

A **local-only** web front end for legal analyst workflows, designed to run on a
local server and act as the UI layer for a larger local AI system.

## Features

- **Sign-in / registration** with session cookies and `bcrypt`-hashed passwords.
- **Local SQLite database** (via SQLAlchemy) — zero-config, file-based, ideal for
  a self-hosted local server. Swap `DATABASE_URL` for PostgreSQL to scale later.
- **Legal analysis workspace**: paste a contract/filing/clause, pick an analysis
  type (summary, risk spotting, clause extraction, obligations), and store the
  result. Each user sees only their own analyses.
- **Pluggable AI backend** (`app/ai_service.py`):
  - `mock` (default) — fully offline heuristic analysis, no external service.
  - `ollama` — calls a local [Ollama](https://ollama.com) server (the "bigger
    local AI system"), falling back to `mock` if unavailable.

## Tech stack

- **Python 3.12** + **FastAPI** (recommended: shares the runtime with the local
  AI stack, so integration is in-process).
- **Jinja2** server-rendered templates + a little CSS (no JS build step).
- **SQLite** + **SQLAlchemy 2.x**.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: customize settings
cp .env.example .env

# Run the dev server (auto-reload). Easiest: works from any directory.
python run.py

# ...or run uvicorn directly (must be from the repo root, with the venv active):
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000, register an account, and run an analysis.

> If you see `Error loading ASGI app. Attribute "app" not found in module
> "app.main"`, uvicorn was started from the wrong directory or without the
> virtualenv active. Use `python run.py` (which pins the working directory), or
> `cd` to the repo root and activate `.venv` before running `uvicorn`.

Override host/port/reload for `run.py` via env vars, e.g. `PORT=9000 RELOAD=0 python run.py`.

### Tests

```bash
pytest -q
```

## Wiring in the real local AI system

Set `AI_BACKEND=ollama` (and `OLLAMA_URL` / `OLLAMA_MODEL`) in `.env`, or extend
`app/ai_service.analyze()` with another local backend (llama.cpp, vLLM, a custom
service). The rest of the app only depends on the `AnalysisResult` it returns.
