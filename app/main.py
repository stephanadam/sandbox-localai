from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from app.ai_service import MODULES
from app.auth import get_current_user
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Document, User
from app.routers import assistant as assistant_router
from app.routers import auth as auth_router
from app.routers import library as library_router
from app.templating import TEMPLATES_DIR, templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

STATIC_DIR = TEMPLATES_DIR.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router.router)
app.include_router(library_router.router)
app.include_router(assistant_router.router)

# Expose app-wide bits to every template.
templates.env.globals["app_tagline"] = settings.app_tagline
templates.env.globals["modules_nav"] = MODULES
templates.env.globals["ai_backend"] = settings.ai_backend
templates.env.globals["cluster_name"] = settings.opensearch_cluster


def _doc_count(user_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(
            select(func.count(Document.id)).where(Document.user_id == user_id)
        ) or 0


templates.env.globals["doc_count"] = _doc_count


@app.get("/")
def index(user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/documents", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name, "ai_backend": settings.ai_backend}
