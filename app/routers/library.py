import os
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

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


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if (r := _require(user)):
        return r
    uploaded = db.scalar(
        select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.kind == "upload"
        )
    ) or 0
    analyzed = db.scalar(
        select(func.count(Document.id)).where(
            Document.user_id == user.id, Document.kind == "analysis"
        )
    ) or 0
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "uploaded": uploaded, "analyzed": analyzed},
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

    files = list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
        ).all()
    )
    q = q.strip()
    if q:
        needle = q.lower()
        files = [
            d for d in files
            if needle in d.title.lower() or needle in (d.original_name or "").lower()
        ]

    return templates.TemplateResponse(
        request, "documents.html", {"user": user, "files": files, "q": q}
    )


@router.get("/documents/{doc_id}", response_class=HTMLResponse)
def document_view(
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
    return templates.TemplateResponse(
        request, "document_view.html", {"user": user, "doc": doc}
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
        kind="upload",
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
    return RedirectResponse(url="/documents", status_code=303)


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
