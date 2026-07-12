# AGENTS.md

## Project

`sandbox-localai` is a **local-only** "Legal Analyst" web app: a FastAPI +
Jinja2 front end backed by SQLite (SQLAlchemy), intended to run on a self-hosted
local server as the UI layer for a larger local AI system. See `README.md` for
the feature list and standard run/test commands.

## Cursor Cloud specific instructions

- **System dependency:** creating the virtualenv requires the `python3.12-venv`
  apt package (not pip-installable). It is already installed in the VM image; if
  `python3 -m venv` ever fails with an `ensurepip is not available` error,
  reinstall it with `sudo apt-get install -y python3.12-venv`.
- **Virtualenv:** dependencies live in `.venv/` (created by the startup update
  script). Activate with `source .venv/bin/activate` before running commands, or
  call binaries directly via `.venv/bin/...`.
- **Run the dev server:** prefer `python run.py` (pins CWD + import path to the
  repo root, so it works from any directory). Direct `uvicorn app.main:app
  --reload --port 8000` also works but **only from the repo root with the venv
  active** — otherwise uvicorn fails with `Error loading ASGI app. Attribute
  "app" not found in module "app.main"`. The SQLite schema is auto-created on
  startup (FastAPI lifespan → `init_db()`), so there is no separate migration
  step. The DB file (`legal_analyst.db`) is git-ignored and created on first run.
- **Tests:** `pytest -q`. The suite forces `DATABASE_URL` to a throwaway temp
  SQLite file and `AI_BACKEND=mock` via env vars set at import time in
  `tests/test_app.py`, so it never touches the dev database.
- **AI backend:** defaults to `AI_BACKEND=mock` (fully offline heuristic analysis
  in `app/ai_service.py`), so the app runs end-to-end with no external service.
  Set `AI_BACKEND=ollama` (+ `OLLAMA_URL`/`OLLAMA_MODEL`) to call a local LLM;
  it falls back to `mock` if the LLM server is unreachable.
