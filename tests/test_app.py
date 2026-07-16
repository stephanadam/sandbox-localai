import io
import os
import tempfile

import pytest

# Use an isolated temp DB / upload dir before importing the app.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
_uploads = tempfile.mkdtemp(prefix="acmeco_uploads_")
_logs = tempfile.mkdtemp(prefix="acmeco_logs_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["AI_BACKEND"] = "mock"
os.environ["UPLOAD_DIR"] = _uploads
os.environ["LOG_DIR"] = _logs

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def _register(client):
    return client.post(
        "/register",
        data={
            "email": "stephan@example.com",
            "full_name": "Stephan Adam",
            "password": "supersecret",
        },
        follow_redirects=True,
    )


def _upload(client, title, content=b"placeholder text", filename=None, ctype="text/plain"):
    resp = client.post(
        "/documents/upload",
        data={"title": title},
        files={"file": (filename or (title + ".txt"), io.BytesIO(content), ctype)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return _doc_id(title)


def _doc_id(title):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Document

    with SessionLocal() as db:
        return db.scalar(
            select(Document.id).where(Document.title == title, Document.kind == "upload")
        )


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["app"] == "AcmeCO"


def test_protected_redirects_when_logged_out(client):
    resp = client.get("/documents", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_register_lands_on_dashboard(client):
    resp = _register(client)
    assert resp.status_code == 200
    assert "Files uploaded" in resp.text
    assert "Files analyzed" in resp.text
    assert "Alternative Finance" not in resp.text


def test_dashboard_shows_agent_specialties(client):
    _register(client)
    page = client.get("/dashboard").text
    assert "AI agents &amp; specialties" in page or "AI agents & specialties" in page
    # Agent role + capability description are present.
    assert "Underwriting &amp; Risk Manager" in page or "Underwriting & Risk Manager" in page
    assert "Capable of:" in page
    assert "creditworthiness" in page  # part of the risk agent's capabilities


def test_chat_shows_starter_prompts(client):
    _register(client)
    _upload(client, "Starter Doc", content=b"revenue and yield content")
    page = client.get("/chat").text
    assert "data-prompt=" in page
    assert "Summarize this document in plain language." in page


def test_nav_has_three_menus(client):
    _register(client)
    page = client.get("/dashboard").text
    assert 'href="/dashboard"' in page
    assert 'href="/documents"' in page
    assert 'href="/chat"' in page


def test_documents_page_has_no_chat_form(client):
    _register(client)
    _upload(client, "Plain Doc", content=b"revenue and yield content")
    page = client.get("/documents").text
    # The chat form lives on /chat, not on /documents.
    assert 'action="/assistant/ask"' not in page
    assert "Plain Doc" in page


def test_chat_page_has_agent_and_file_pickers(client):
    _register(client)
    _upload(client, "Chatable Doc", content=b"revenue and yield content")
    page = client.get("/chat").text
    assert 'name="agent_key"' in page
    assert 'name="document_id"' in page
    assert "Chatable Doc" in page


def test_ask_saves_response_as_analysis_document(client):
    _register(client)
    content = b"Revenue-based yields of 8-12%. IRR strong. Risk of breach and default."
    doc_id = _upload(client, "Royalty Guide", content=content)

    resp = client.post(
        "/assistant/ask",
        data={"question": "Summarize risks.", "agent_key": "finance",
              "document_id": str(doc_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Landed on the chat page showing the answer.
    assert "Finance Specialist" in resp.text
    assert "Summarize risks." in resp.text

    # An analysis document + text file were created.
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Document

    with SessionLocal() as db:
        analysis = db.scalars(
            select(Document).where(Document.kind == "analysis")
        ).all()
    assert analysis, "expected an analysis document to be saved"
    saved = analysis[-1]
    assert "Royalty Guide" in saved.title
    assert os.path.exists(saved.stored_path)
    with open(saved.stored_path, encoding="utf-8") as fh:
        assert "Finance Specialist" in fh.read()

    # The analysis document shows in the Documents list, tagged as Analysis.
    docs_page = client.get("/documents").text
    assert "Analysis" in docs_page


def test_conversation_is_per_file(client):
    _register(client)
    a_id = _upload(client, "Alpha Memo", content=b"Alpha revenue and yield details.")
    b_id = _upload(client, "Beta Memo", content=b"Beta market and funding details.")

    client.post(
        "/assistant/ask",
        data={"question": "ALPHA_QUESTION_MARKER", "agent_key": "finance",
              "document_id": str(a_id)},
        follow_redirects=True,
    )
    client.post(
        "/assistant/ask",
        data={"question": "BETA_QUESTION_MARKER", "agent_key": "legal",
              "document_id": str(b_id)},
        follow_redirects=True,
    )

    a_page = client.get(f"/chat?doc={a_id}").text
    assert "ALPHA_QUESTION_MARKER" in a_page
    assert "BETA_QUESTION_MARKER" not in a_page

    b_page = client.get(f"/chat?doc={b_id}").text
    assert "BETA_QUESTION_MARKER" in b_page
    assert "ALPHA_QUESTION_MARKER" not in b_page


def test_ask_without_valid_document_redirects(client):
    _register(client)
    resp = client.post(
        "/assistant/ask",
        data={"question": "no file selected", "agent_key": "finance", "document_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/chat"


def test_bad_login_rejected(client):
    resp = client.post(
        "/login", data={"email": "nobody@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_delete_document_removes_file_and_conversation(client):
    _register(client)
    doc_id = _upload(client, "Disposable Memo", content=b"temporary content revenue")
    client.post(
        "/assistant/ask",
        data={"question": "anything?", "agent_key": "finance",
              "document_id": str(doc_id)},
        follow_redirects=True,
    )

    from sqlalchemy import func, select

    from app.database import SessionLocal
    from app.models import ChatMessage, Document

    with SessionLocal() as db:
        assert db.get(Document, doc_id) is not None

    resp = client.post(f"/documents/{doc_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/documents"

    with SessionLocal() as db:
        assert db.get(Document, doc_id) is None
        remaining = db.scalar(
            select(func.count(ChatMessage.id)).where(ChatMessage.document_id == doc_id)
        )
        assert remaining == 0

    # The deleted document's row/link is gone from the library.
    assert f'/documents/{doc_id}"' not in client.get("/documents").text


def test_attached_document_with_no_text_message(client):
    _register(client)
    doc_id = _upload(
        client, "Scanned Deck", content=b"not a real pdf body",
        filename="deck.pdf", ctype="application/pdf",
    )
    resp = client.post(
        "/assistant/ask",
        data={"question": "What does this contain?", "agent_key": "legal",
              "document_id": str(doc_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "no extractable text" in resp.text


def test_audit_log_written(client):
    _register(client)
    log_path = os.path.join(_logs, "acmeco.log")
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as fh:
        contents = fh.read()
    assert "login.success" in contents or "register.success" in contents
    assert "document.upload" in contents
    assert "assistant.ask" in contents
    assert "assistant.response" in contents
    assert "document.analysis_saved" in contents
