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
        return db.scalar(select(Document.id).where(Document.title == title))


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
    assert "Go to Documents" in resp.text
    # Sidebar cluster status is present; module folders are gone.
    assert "Cluster:" in resp.text
    assert "Alternative Finance" not in resp.text


def test_upload_document_and_ask_agent(client):
    _register(client)  # ensure logged in (session persists in TestClient)

    content = (
        b"This royalty financing agreement offers revenue-based yields of 8-12%. "
        b"The parties agree to indemnify against liability and breach. IRR and ROI "
        b"projections are strong."
    )
    doc_id = _upload(client, "Royalty Financing Guide 2026", content=content)
    assert doc_id is not None

    # The uploaded file's conversation view is shown.
    page = client.get(f"/documents?doc={doc_id}").text
    assert "Royalty Financing Guide 2026" in page
    assert "Conversation for: Royalty Financing Guide 2026" in page

    resp = client.post(
        "/assistant/ask",
        data={
            "question": "Summarize the yields and key risks.",
            "agent_key": "finance",
            "document_id": str(doc_id),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    text = resp.text
    assert "Finance Specialist" in text
    assert "Summarize the yields and key risks." in text
    assert "Reviewed the attached document" in text


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

    a_page = client.get(f"/documents?doc={a_id}").text
    assert "ALPHA_QUESTION_MARKER" in a_page
    assert "BETA_QUESTION_MARKER" not in a_page

    b_page = client.get(f"/documents?doc={b_id}").text
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
    assert resp.headers["location"] == "/documents"


def test_search_filters_documents(client):
    _register(client)
    resp = client.get("/documents", params={"q": "nonexistentxyz"})
    assert resp.status_code == 200
    assert "Royalty Financing Guide 2026" not in resp.text


def test_bad_login_rejected(client):
    resp = client.post(
        "/login", data={"email": "nobody@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_attached_document_with_no_text_message(client):
    _register(client)
    # A .pdf whose bytes aren't a real PDF, so extraction yields no text.
    doc_id = _upload(
        client, "Scanned Deck", content=b"not a real pdf body",
        filename="deck.pdf", ctype="application/pdf",
    )
    assert doc_id is not None

    resp = client.post(
        "/assistant/ask",
        data={
            "question": "What does this contain?",
            "agent_key": "legal",
            "document_id": str(doc_id),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "no extractable text" in resp.text


def test_chat_form_has_document_picker(client):
    _register(client)
    doc_id = _upload(client, "Picker Memo", content=b"content for picker test")
    page = client.get(f"/documents?doc={doc_id}").text
    assert 'name="document_id"' in page
    assert "Picker Memo" in page


def test_delete_document_removes_file_and_conversation(client):
    _register(client)
    doc_id = _upload(client, "Disposable Memo", content=b"temporary content revenue")

    # Create a conversation for it.
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
        msg_count = db.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.document_id == doc_id
            )
        )
        assert msg_count and msg_count > 0

    # Delete it.
    resp = client.post(f"/documents/{doc_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/documents"

    with SessionLocal() as db:
        assert db.get(Document, doc_id) is None
        remaining = db.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.document_id == doc_id
            )
        )
        assert remaining == 0

    # It no longer appears in the library.
    assert "Disposable Memo" not in client.get("/documents").text


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
