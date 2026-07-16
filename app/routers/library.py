import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai_service import AGENTS, DEFAULT_AGENT
from app.audit import log_event
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.extract import extract_text
from app.models import ChatMessage, Document, User
from app.templating import templates

router = APIRouter()


def _require(user: User | None):
    return None if user else RedirectResponse(url="/login", status_code=303)


def _user_documents(db: Session, user_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r
    total = db.scalar(
        select(func.count(Document.id)).where(Document.user_id == user.id)
    ) or 0
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "total": total}
    )


@router.get("/documents", response_class=HTMLResponse)
def documents(
    request: Request,
    q: str = "",
    doc: str = "",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r

    files = _user_documents(db, user.id)

    q = q.strip()
    if q:
        needle = q.lower()
        files = [
            d for d in files
            if needle in d.title.lower() or needle in (d.original_name or "").lower()
        ]

    # Resolve the active file (per-file conversation). Default to the newest.
    active: Document | None = None
    if doc.strip().isdigit():
        candidate = db.get(Document, int(doc))
        if candidate and candidate.user_id == user.id:
            active = candidate
    if active is None and files:
        active = files[0]

    messages = []
    if active is not None:
        messages = db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user.id,
                ChatMessage.document_id == active.id,
            )
            .order_by(ChatMessage.created_at.asc())
        ).all()

    return templates.TemplateResponse(
        request,
        "documents.html",
        {
            "user": user,
            "files": files,
            "agents": AGENTS,
            "default_agent": DEFAULT_AGENT,
            "active": active,
            "messages": messages,
            "q": q,
        },
    )


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    title: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r

    data = await file.read()
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
    stored_path = os.path.join(settings.upload_dir, safe_name)
    with open(stored_path, "wb") as fh:
        fh.write(data)

    text = extract_text(data, file.filename or "", file.content_type or "")
    doc = Document(
        user_id=user.id,
        title=(title.strip() or (file.filename or "Untitled document")),
        original_name=file.filename or "",
        stored_path=stored_path,
        content_type=file.content_type or "",
        size_bytes=len(data),
        extracted_text=text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_event(
        "document.upload",
        user=user.email,
        title=doc.title,
        filename=doc.original_name,
        size_bytes=doc.size_bytes,
        extracted_chars=len(text),
    )
    # Open the freshly uploaded file's conversation.
    return RedirectResponse(url=f"/documents?doc={doc.id}", status_code=303)


@router.post("/documents/{doc_id}/delete")
def delete_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r

    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        return RedirectResponse(url="/documents", status_code=303)

    # Remove the file's conversation, the stored file on disk, then the record.
    db.execute(
        delete(ChatMessage).where(
            ChatMessage.document_id == doc.id, ChatMessage.user_id == user.id
        )
    )
    if doc.stored_path and os.path.exists(doc.stored_path):
        try:
            os.remove(doc.stored_path)
        except OSError:
            pass
    title = doc.title
    db.delete(doc)
    db.commit()
    log_event("document.delete", user=user.email, title=title, document_id=doc_id)
    return RedirectResponse(url="/documents", status_code=303)
