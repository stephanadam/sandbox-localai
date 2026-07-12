from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import get_current_user
from app.config import settings
from app.database import init_db
from app.models import User
from app.routers import analysis as analysis_router
from app.routers import auth as auth_router
from app.templating import TEMPLATES_DIR  # noqa: F401 (ensures templates dir exists)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

STATIC_DIR = TEMPLATES_DIR.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router.router)
app.include_router(analysis_router.router)


@app.get("/")
def index(user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz")
def healthz(request: Request):
    return {"status": "ok", "app": settings.app_name, "ai_backend": settings.ai_backend}
