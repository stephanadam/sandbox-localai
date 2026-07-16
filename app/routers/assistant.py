import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.ai_service import agent_or_default, ask_agent
from app.audit import log_event
from app.auth import get_current_user
from app.database import get_db
from app.extract import extract_text
from app.models import ChatMessage, Document, User

router = APIRouter()


def _resolve_context(db: Session, doc: Document) -> str:
    """Return the document's text, re-extracting from disk if needed.

    Older uploads (or uploads made before a parser was available) may have empty
    ``extracted_text``. Try reading the stored file again so an attached document
    actually supports the request instead of silently being ignored.
    """
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


@router.post("/assistant/ask")
def ask(
    request: Request,
    question: str = Form(...),
    agent_key: str = Form("finance"),
    document_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)

    question = question.strip()
    if not question:
        return RedirectResponse(url="/documents", status_code=303)

    agent_key = agent_or_default(agent_key)

    # Conversations are scoped to a single text file; a valid file is required.
    doc: Document | None = None
    doc_id_int: int | None = None
    if document_id.strip().isdigit():
        candidate = db.get(Document, int(document_id))
        if candidate and candidate.user_id == user.id:
            doc = candidate
            doc_id_int = candidate.id
    if doc is None:
        log_event(
            "assistant.document_missing",
            user=user.email,
            requested_document_id=document_id,
        )
        return RedirectResponse(url="/documents", status_code=303)

    db.add(
        ChatMessage(
            user_id=user.id,
            agent_key=agent_key,
            sender="user",
            content=question,
            document_id=doc_id_int,
        )
    )
    db.commit()

    context = _resolve_context(db, doc)
    log_event(
        "assistant.ask",
        user=user.email,
        agent=agent_key,
        document=doc.title,
        document_id=doc_id_int,
        context_chars=(len(context) if context else 0),
        question=question,
    )

    reply = ask_agent(agent_key, question, context, document_title=doc.title)

    db.add(
        ChatMessage(
            user_id=user.id,
            agent_key=agent_key,
            sender="assistant",
            content=reply.text,
            document_id=doc_id_int,
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
    return RedirectResponse(url=f"/documents?doc={doc_id_int}#assistant", status_code=303)
