"""Independent runtime checks for CSRF/referer/cookie/connect contracts."""
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from fastapi import Response
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient


load_dotenv("/app/backend/.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _base_url() -> str:
    with open("/app/frontend/.env", encoding="utf-8") as frontend_env:
        for line in frontend_env:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _base_url()
TEST_USER_ID = "TEST_security_runtime_contract"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture
def auth_csrf_client(db):
    db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {"id": TEST_USER_ID, "email": os.environ["ALLOWED_USER_EMAIL"], "name": "Security Runtime"}},
        upsert=True,
    )
    session_id = secrets.token_urlsafe(32)
    db.sessions.insert_one(
        {
            "session_id": session_id,
            "user_id": TEST_USER_ID,
            "auth_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "pytest-security-runtime-contract",
        }
    )
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(session_id)
    client = requests.Session()
    client.headers.update({"Origin": BASE_URL})
    client.cookies.set("nova_session", cookie)
    csrf = client.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    client.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    yield client
    db.notes.delete_many({"user_id": TEST_USER_ID})
    db.google_oauth_states.delete_many({"user_id": TEST_USER_ID})
    db.sessions.delete_one({"session_id": session_id})
    db.users.delete_one({"id": TEST_USER_ID})


def test_cookie_helper_has_all_security_flags_including_max_age():
    from server import set_session_cookie

    response = Response()
    set_session_cookie(response, "signed-test-value")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "max-age=" in cookie


def test_bad_referer_with_valid_cookie_and_csrf_is_blocked(auth_csrf_client):
    response = auth_csrf_client.post(
        f"{BASE_URL}/api/notes",
        json={"title": "bad referer", "content": "must fail"},
        headers={"Referer": "https://evil.example/some/path"},
        timeout=30,
    )
    assert response.status_code == 403
    assert response.json().get("detail") == "Referer reddedildi"


def test_google_connect_get_disabled_and_post_enabled(auth_csrf_client):
    get_response = auth_csrf_client.get(f"{BASE_URL}/api/google/connect", timeout=30)
    assert get_response.status_code == 405

    post_response = auth_csrf_client.post(f"{BASE_URL}/api/google/connect", timeout=30)
    assert post_response.status_code == 200
    data = post_response.json()
    assert "url" in data
    assert "accounts.google.com" in data["url"]
