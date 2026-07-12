from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.ai_service import agent_or_default, ask_agent
from app.auth import get_current_user
from app.database import get_db
from app.models import ChatMessage, Document, User

router = APIRouter()


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
        doc = db.get(Document, int(document_id))
        if doc and doc.user_id == user.id:
            doc_id_int = doc.id
        else:
            doc = None

    db.add(
        ChatMessage(
            user_id=user.id,
            agent_key=agent_key,
            sender="user",
            content=question,
            document_id=doc_id_int,
        )
    )

    context = doc.extracted_text if doc else None
    reply = ask_agent(agent_key, question, context)

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
    return RedirectResponse(url="/documents#assistant", status_code=303)
