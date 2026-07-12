import os
import tempfile

import pytest

# Use an isolated temp SQLite DB per test session before importing the app.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["AI_BACKEND"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_route_redirects_when_logged_out(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_register_login_and_analyze_flow(client):
    # Register (auto-logs in) -> lands on dashboard.
    resp = client.post(
        "/register",
        data={
            "email": "analyst@example.com",
            "full_name": "Jane Analyst",
            "password": "supersecret",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Welcome" in resp.text

    # Run a legal analysis (core feature).
    resp = client.post(
        "/analyze",
        data={
            "title": "Test NDA",
            "analysis_type": "risks",
            "source_text": (
                "This Agreement shall terminate upon breach. The parties agree "
                "to indemnify each other against all liability and damages."
            ),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Analysis result" in resp.text
    assert "liability" in resp.text.lower()

    # It shows on the dashboard.
    resp = client.get("/dashboard")
    assert "Test NDA" in resp.text


def test_duplicate_registration_rejected(client):
    client.post(
        "/register",
        data={"email": "dup@example.com", "full_name": "", "password": "password1"},
    )
    resp = client.post(
        "/register",
        data={"email": "dup@example.com", "full_name": "", "password": "password1"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.text


def test_bad_login_rejected(client):
    resp = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text
