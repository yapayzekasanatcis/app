"""Security regression tests for browser-facing NOVA endpoints."""
import asyncio
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from fastapi import HTTPException, Response
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = ""
with open("/app/frontend/.env") as frontend_env:
    for line in frontend_env:
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

ORIGIN = BASE_URL
TEST_USER_ID = "TEST_security_controls"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture
def security_client(db):
    db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {"id": TEST_USER_ID, "email": os.environ["ALLOWED_USER_EMAIL"], "name": "Security Test"}},
        upsert=True,
    )
    session_id = secrets.token_urlsafe(32)
    db.sessions.insert_one({
        "session_id": session_id,
        "user_id": TEST_USER_ID,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-security-controls",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(session_id)
    client = requests.Session()
    client.headers.update({"Origin": ORIGIN})
    client.cookies.set("nova_session", cookie)
    csrf = client.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    client.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    yield client
    db.notes.delete_many({"user_id": TEST_USER_ID})
    db.sessions.delete_one({"session_id": session_id})
    db.users.delete_one({"id": TEST_USER_ID})


def test_cors_exact_allowlist_and_negative_origin():
    allowed = requests.get(f"{BASE_URL}/api/", headers={"Origin": ORIGIN}, timeout=30)
    assert allowed.status_code == 200
    assert allowed.headers.get("Access-Control-Allow-Origin") == ORIGIN
    assert allowed.headers.get("Access-Control-Allow-Credentials") == "true"
    assert allowed.headers.get("Access-Control-Allow-Origin") != "*"

    rejected = requests.get(f"{BASE_URL}/api/", headers={"Origin": "https://evil.example"}, timeout=30)
    assert rejected.status_code == 403
    assert rejected.headers.get("Access-Control-Allow-Origin") != "https://evil.example"


def test_cors_preflight_rejects_unexpected_origin():
    headers = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    response = requests.options(f"{BASE_URL}/api/notes", headers=headers, timeout=30)
    assert response.headers.get("Access-Control-Allow-Origin") != "https://evil.example"
    assert response.headers.get("Access-Control-Allow-Credentials") != "true"


def test_csrf_missing_invalid_and_valid_write(security_client, db):
    valid_token = security_client.headers.pop("X-CSRF-Token")
    missing = security_client.post(f"{BASE_URL}/api/notes", json={"content": "must fail"}, timeout=30)
    assert missing.status_code == 403
    assert missing.json()["detail"] == "CSRF doğrulaması başarısız"

    security_client.headers["X-CSRF-Token"] = "invalid-token"
    invalid = security_client.post(f"{BASE_URL}/api/notes", json={"content": "must fail"}, timeout=30)
    assert invalid.status_code == 403

    security_client.headers["X-CSRF-Token"] = valid_token
    valid = security_client.post(f"{BASE_URL}/api/notes", json={"content": "temporary secure note"}, timeout=30)
    assert valid.status_code == 200, valid.text
    deleted = security_client.delete(f"{BASE_URL}/api/notes/{valid.json()['id']}", timeout=30)
    assert deleted.status_code == 200
    assert db.notes.count_documents({"user_id": TEST_USER_ID, "content": "temporary secure note"}) == 0


def test_csrf_token_is_not_cacheable(security_client):
    response = security_client.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert response.status_code == 200
    assert response.headers.get("Cache-Control", "").startswith("no-store")


def test_cookie_security_flags():
    from server import set_session_cookie

    response = Response()
    set_session_cookie(response, "signed-test-value")
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_error_messages_are_redacted(monkeypatch):
    import server

    async def broken_create(**_kwargs):
        raise RuntimeError("internal-secret-provider-detail")

    monkeypatch.setattr(server.openai_client.audio.speech, "create", broken_create)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(server.tts(text="Güvenli hata testi", user={"id": TEST_USER_ID}))
    assert raised.value.detail == "Ses şu anda üretilemedi"
    assert "internal-secret" not in raised.value.detail


def test_rate_limit_on_tts_without_provider_cost(security_client):
    statuses = [
        security_client.post(f"{BASE_URL}/api/voice/tts", data={}, timeout=30).status_code
        for _ in range(22)
    ]
    assert statuses[0] == 422
    assert 429 in statuses


def test_security_headers_on_api_and_frontend():
    required = {
        "content-security-policy",
        "strict-transport-security",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
        "x-frame-options",
    }
    cache_buster = secrets.token_hex(6)
    for url in (f"{BASE_URL}/api/?security_probe={cache_buster}", f"{BASE_URL}/?security_probe={cache_buster}"):
        for attempt in range(3):
            response = requests.get(
                f"{url}&attempt={attempt}",
                headers={"Cache-Control": "no-cache", "Origin": ORIGIN},
                timeout=30,
            )
            if required.issubset({name.lower() for name in response.headers.keys()}):
                break
        assert response.status_code == 200
        assert required.issubset({name.lower() for name in response.headers.keys()})
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_google_connect_get_is_disabled(security_client):
    connect_get = security_client.get(f"{BASE_URL}/api/google/connect", timeout=30)
    assert connect_get.status_code == 405
