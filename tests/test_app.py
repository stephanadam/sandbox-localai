import io
import os
import tempfile

import pytest

# Use an isolated temp DB / upload dir before importing the app.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
_uploads = tempfile.mkdtemp(prefix="acmeco_uploads_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["AI_BACKEND"] = "mock"
os.environ["UPLOAD_DIR"] = _uploads

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


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["app"] == "AcmeCO"


def test_protected_redirects_when_logged_out(client):
    resp = client.get("/documents", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_register_shows_library(client):
    resp = _register(client)
    assert resp.status_code == 200
    assert "Document Library" in resp.text
    # Sidebar shows the modules and the connected cluster status.
    assert "Alternative Finance" in resp.text
    assert "Cluster:" in resp.text


def test_upload_document_and_ask_agent(client):
    _register(client)  # ensure logged in (session persists in TestClient)

    content = (
        b"This royalty financing agreement offers revenue-based yields of 8-12%. "
        b"The parties agree to indemnify against liability and breach. IRR and ROI "
        b"projections are strong."
    )
    resp = client.post(
        "/documents/upload",
        data={"module": "alternative_finance", "title": "Royalty Financing Guide 2026"},
        files={"file": ("royalty.txt", io.BytesIO(content), "text/plain")},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Royalty Financing Guide 2026" in resp.text

    # Find the uploaded document id from the library page select options.
    page = client.get("/documents").text
    assert "Royalty Financing Guide 2026" in page

    # Ask the finance agent about the document.
    resp = client.post(
        "/assistant/ask",
        data={
            "question": "Summarize the yields and key risks.",
            "agent_key": "finance",
            "document_id": "1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    text = resp.text
    assert "Finance Specialist" in text
    assert "Summarize the yields and key risks." in text
    # Mock backend echoes detected terms from the document context.
    assert "Reviewed the attached document" in text


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
