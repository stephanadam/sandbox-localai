#!/usr/bin/env python3
"""Convenience dev launcher for the Legal Analyst app.

Run from anywhere: `python run.py`. This avoids the common
`Error loading ASGI app. Attribute "app" not found in module "app.main"`
mistake, which happens when uvicorn is started from the wrong working
directory. We pin the working directory and import path to this file's
folder (the repo root) so `app.main:app` always resolves.

Environment overrides: HOST (default 0.0.0.0), PORT (default 8000),
RELOAD (default 1; set to 0 to disable auto-reload).
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import uvicorn  # noqa: E402  (import after sys.path fix)


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") not in ("0", "false", "False")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
