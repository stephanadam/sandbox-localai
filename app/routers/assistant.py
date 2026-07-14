import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
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

    doc: Document | None = None
    doc_id_int: int | None = None
    if document_id.strip().isdigit():
        candidate = db.get(Document, int(document_id))
        if candidate and candidate.user_id == user.id:
            doc = candidate
            doc_id_int = candidate.id
        else:
            log_event(
                "assistant.document_missing",
                user=user.email,
                requested_document_id=document_id,
            )

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

    context = _resolve_context(db, doc) if doc else None
    log_event(
        "assistant.ask",
        user=user.email,
        agent=agent_key,
        document=(doc.title if doc else None),
        document_id=doc_id_int,
        context_chars=(len(context) if context else 0),
        question=question,
    )

    reply = ask_agent(
        agent_key,
        question,
        context,
        document_title=(doc.title if doc else None),
    )

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
    return RedirectResponse(url="/documents#assistant", status_code=303)


@router.post("/assistant/preferences")
async def save_preferences(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Persist the user's custom assistant-panel size (from the resize handle)."""
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    payload = await request.json()

    def _clamp(value, lo, hi):
        try:
            return max(lo, min(hi, int(round(float(value)))))
        except (TypeError, ValueError):
            return None

    width = _clamp(payload.get("width"), 300, 1200)
    height = _clamp(payload.get("height"), 300, 2000)

    if width is not None:
        user.assistant_width = width
    if height is not None:
        user.assistant_height = height
    db.add(user)
    db.commit()
    log_event(
        "assistant.preferences",
        user=user.email,
        width=user.assistant_width,
        height=user.assistant_height,
    )
    return JSONResponse(
        {"width": user.assistant_width, "height": user.assistant_height}
    )
