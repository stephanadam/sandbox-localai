# AGENTS.md

## Project

`sandbox-localai` is **AcmeCO**, a **local-only** financial/legal document
workspace: a FastAPI + Jinja2 (dark UI) front end backed by SQLite (SQLAlchemy),
intended to run on a self-hosted local server as the UI layer for a larger local
AI system. Core pieces: sign-in, a document library organized into modules
(`app/ai_service.py` → `MODULES`), document upload + text extraction
(`app/extract.py`), and a RAG assistant that routes questions to one of seven
specialist agents (`app/ai_service.py` → `AGENTS`). See `README.md` for the
feature list and standard run/test commands.

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
- **AI backend:** `ask_agent()` in `app/ai_service.py` is the only integration
  point with the "bigger local AI system". Defaults to `AI_BACKEND=mock` (fully
  offline, agent-aware heuristic), so the app runs end-to-end with no external
  service. Set `AI_BACKEND=ollama` (+ `OLLAMA_URL`/`OLLAMA_MODEL`) or
  `AI_BACKEND=anythingllm` (+ `ANYTHINGLLM_URL`/`ANYTHINGLLM_API_KEY`/
  `ANYTHINGLLM_WORKSPACE`) to use a real LLM; both **fall back to `mock`** on any
  error, so a missing/broken AI service never breaks the UI.
- **Uploads:** stored under `UPLOAD_DIR` (default `./uploads/`, git-ignored);
  extracted text is saved on the `Document` row and passed to the agent as RAG
  context. PDF/DOCX/XLSX parsing needs `pypdf`/`python-docx`/`openpyxl` (in
  `requirements.txt`); extraction fails soft (empty text) for unsupported files.
- **Keep this app in its own venv.** Do not `pip install -r requirements.txt`
  into an environment that also runs the Chainlit/CrewAI local-AI stack — the
  pinned web deps (fastapi/starlette/uvicorn/pydantic-settings) will downgrade
  packages that stack requires. Use a dedicated venv (e.g. `.venv-legal/`).
