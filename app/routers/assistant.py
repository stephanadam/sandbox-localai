import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_service import (
    AGENTS,
    DEFAULT_AGENT,
    LLM_TARGETS,
    STARTER_PROMPTS,
    agent_or_default,
    ask_agent,
    target_or_default,
)
from app.audit import log_event
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.extract import extract_text
from app.models import ChatMessage, Document, User
from app.templating import templates

router = APIRouter()


def _resolve_context(db: Session, doc: Document) -> str:
    """Return the document's text, re-extracting from disk if needed."""
    if doc.extracted_text:
        return doc.extracted_text
    if doc.stored_path and os.path.exists(doc.stored_path):
        try:
            with open(doc.stored_path, "rb") as fh:
                data = fh.read()
            text = extract_text(data, doc.original_name or "", doc.content_type or "")
        except OSError:
            text = ""
        if text:
            doc.extracted_text = text
            db.add(doc)
            db.commit()
        return text
    return ""


_SOURCE_KINDS = ("upload", "edgar")


def _source_documents(db: Session, user_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user_id, Document.kind.in_(_SOURCE_KINDS))
            .order_by(Document.created_at.desc())
        ).all()
    )


@router.get("/chat", response_class=HTMLResponse)
def chat_page(
    request: Request,
    doc: str = "",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    files = _source_documents(db, user.id)

    active: Document | None = None
    if doc.strip().isdigit():
        candidate = db.get(Document, int(doc))
        if candidate and candidate.user_id == user.id and candidate.kind in _SOURCE_KINDS:
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
        "chat.html",
        {
            "user": user,
            "files": files,
            "agents": AGENTS,
            "default_agent": DEFAULT_AGENT,
            "active": active,
            "messages": messages,
            "starter_prompts": STARTER_PROMPTS,
            "llm_targets": LLM_TARGETS,
            "default_target": target_or_default(None),
        },
    )


def _save_analysis_file(
    db: Session, user: User, source: Document, agent_key: str,
    question: str, response_text: str,
) -> Document:
    """Persist an AI response as a TEXT file + an 'analysis' Document record."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    role = AGENTS[agent_key]["role"]
    body = (
        f"Analysis by: {role}\n"
        f"Source document: {source.title}\n"
        f"Question: {question}\n"
        f"Generated: {stamp} UTC\n"
        f"{'-' * 60}\n\n{response_text}\n"
    )
    filename = f"analysis_{uuid.uuid4().hex}.txt"
    stored_path = os.path.join(settings.upload_dir, filename)
    with open(stored_path, "w", encoding="utf-8") as fh:
        fh.write(body)

    title = f"Analysis: {source.title} — {question[:40]}".strip()
    analysis = Document(
        user_id=user.id,
        kind="analysis",
        title=title,
        original_name=filename,
        stored_path=stored_path,
        content_type="text/plain",
        size_bytes=len(body.encode("utf-8")),
        extracted_text=body,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    log_event(
        "document.analysis_saved",
        user=user.email,
        title=analysis.title,
        source=source.title,
        path=stored_path,
    )
    return analysis


@router.post("/assistant/ask")
def ask(
    request: Request,
    question: str = Form(...),
    agent_key: str = Form("finance"),
    document_id: str = Form(""),
    llm_target: str = Form(""),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    question = question.strip()
    if not question:
        return RedirectResponse(url="/chat", status_code=303)

    agent_key = agent_or_default(agent_key)
    target = target_or_default(llm_target)

    # Conversations are scoped to a single source file; a valid file is required.
    doc: Document | None = None
    if document_id.strip().isdigit():
        candidate = db.get(Document, int(document_id))
        if candidate and candidate.user_id == user.id and candidate.kind in _SOURCE_KINDS:
            doc = candidate
    if doc is None:
        log_event(
            "assistant.document_missing",
            user=user.email,
            requested_document_id=document_id,
        )
        return RedirectResponse(url="/chat", status_code=303)

    db.add(
        ChatMessage(
            user_id=user.id,
            agent_key=agent_key,
            sender="user",
            content=question,
            document_id=doc.id,
        )
    )
    db.commit()

    context = _resolve_context(db, doc)
    log_event(
        "assistant.ask",
        user=user.email,
        agent=agent_key,
        document=doc.title,
        document_id=doc.id,
        context_chars=(len(context) if context else 0),
        target=target,
        question=question,
    )

    reply = ask_agent(agent_key, question, context, document_title=doc.title, target=target)

    db.add(
        ChatMessage(
            user_id=user.id,
            agent_key=agent_key,
            sender="assistant",
            content=reply.text,
            document_id=doc.id,
            backend=reply.backend,
        )
    )
    db.commit()
    log_event(
        "assistant.response",
        user=user.email,
        agent=agent_key,
        backend=reply.backend,
        response=reply.text,
    )

    # Persist the response as a TEXT file + analysis document (revisit in Documents).
    _save_analysis_file(db, user, doc, agent_key, question, reply.text)

    return RedirectResponse(url=f"/chat?doc={doc.id}#assistant", status_code=303)
