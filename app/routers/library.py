import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_service import AGENTS, DEFAULT_AGENT, MODULES
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.extract import extract_text
from app.models import ChatMessage, Document, User
from app.templating import templates

router = APIRouter()


def _require(user: User | None):
    return None if user else RedirectResponse(url="/login", status_code=303)


def _docs_by_module(db: Session, user_id: int) -> dict[str, list[Document]]:
    docs = db.scalars(
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    ).all()
    grouped: dict[str, list[Document]] = {key: [] for key in MODULES}
    for d in docs:
        grouped.setdefault(d.module, []).append(d)
    return grouped


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r
    grouped = _docs_by_module(db, user.id)
    total = sum(len(v) for v in grouped.values())
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "grouped": grouped, "modules": MODULES, "total": total},
    )


@router.get("/documents", response_class=HTMLResponse)
def documents(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r
    grouped = _docs_by_module(db, user.id)
    q = q.strip()
    if q:
        needle = q.lower()
        grouped = {
            key: [d for d in docs if needle in d.title.lower()
                  or needle in (d.original_name or "").lower()]
            for key, docs in grouped.items()
        }
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "documents.html",
        {
            "user": user,
            "grouped": grouped,
            "modules": MODULES,
            "agents": AGENTS,
            "default_agent": DEFAULT_AGENT,
            "messages": messages,
            "documents_flat": [d for docs in grouped.values() for d in docs],
            "q": q,
        },
    )


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    module: str = Form(...),
    title: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r
    if module not in MODULES:
        module = next(iter(MODULES))

    data = await file.read()
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
    stored_path = os.path.join(settings.upload_dir, safe_name)
    with open(stored_path, "wb") as fh:
        fh.write(data)

    text = extract_text(data, file.filename or "", file.content_type or "")
    doc = Document(
        user_id=user.id,
        module=module,
        title=(title.strip() or (file.filename or "Untitled document")),
        original_name=file.filename or "",
        stored_path=stored_path,
        content_type=file.content_type or "",
        size_bytes=len(data),
        extracted_text=text,
    )
    db.add(doc)
    db.commit()
    return RedirectResponse(url="/documents", status_code=303)
