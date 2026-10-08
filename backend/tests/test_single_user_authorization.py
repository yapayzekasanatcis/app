"""Single-user authorization contract for NOVA production access."""
import asyncio
import hashlib
import hmac
import os
import secrets
import sys
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

import httpx
import pytest
import requests
from dotenv import load_dotenv
from fastapi import HTTPException, Response
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient


load_dotenv("/app/backend/.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import google_integration as gint
import server
from auth_policy import ALLOWED_USER_EMAIL, UNAUTHORIZED_MESSAGE


def _base_url() -> str:
    with open("/app/frontend/.env", encoding="utf-8") as frontend_env:
        for line in frontend_env:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE_URL = _base_url()


class _ProviderResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _provider_client(payload):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return _ProviderResponse(payload)

    return FakeAsyncClient


class _FakeCollection:
    def __init__(self):
        self.rows = []

    async def update_one(self, query, update, upsert=False):
        row = next((item for item in self.rows if all(item.get(k) == v for k, v in query.items())), None)
        if row:
            row.update(update.get("$set", {}))
        elif upsert:
            self.rows.append({**query, **update.get("$set", {})})

    async def insert_one(self, document):
        self.rows.append(dict(document))


class _FakeDb:
    def __init__(self):
        self.users = _FakeCollection()
        self.sessions = _FakeCollection()


def test_allowed_google_account_completes_local_session(monkeypatch):
    fake_db = _FakeDb()
    payload = {
        "id": "allowed-provider-user",
        "email": ALLOWED_USER_EMAIL,
        "email_verified": True,
        "name": "Bora Ünsal",
        "picture": None,
    }
    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server.httpx, "AsyncClient", _provider_client(payload))

    response = Response()
    result = asyncio.run(server.auth_session(server.SessionExchange(session_id="allowed"), response))

    assert result["email"] == ALLOWED_USER_EMAIL
    assert fake_db.users.rows[0]["email_verified"] is True
    assert len(fake_db.sessions.rows) == 1
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    signed = cookie["nova_session"].value
    session_id = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).loads(signed)
    assert session_id == fake_db.sessions.rows[0]["session_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"id": "intruder", "email": "baska-hesap@example.com", "email_verified": True},
        {"id": "unverified", "email": ALLOWED_USER_EMAIL, "email_verified": False},
    ],
)
def test_other_or_unverified_google_account_is_rejected_before_session(monkeypatch, payload):
    fake_db = _FakeDb()
    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server.httpx, "AsyncClient", _provider_client(payload))

    with pytest.raises(HTTPException) as raised:
        asyncio.run(server.auth_session(server.SessionExchange(session_id="denied"), Response()))

    assert raised.value.status_code == 403
    assert raised.value.detail == UNAUTHORIZED_MESSAGE
    assert fake_db.users.rows == []
    assert fake_db.sessions.rows == []


def _csrf_token(session_id: str) -> str:
    secret = os.environ["SESSION_SECRET"]
    subject = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return URLSafeTimedSerializer(secret, salt="nova-csrf-v1").dumps(subject)


def test_private_and_paid_endpoints_stop_unauthorized_user_before_providers(monkeypatch):
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    user_id = f"TEST_unauthorized_{secrets.token_hex(6)}"
    db.users.insert_one({
        "id": user_id,
        "email": "unauthorized@example.com",
        "name": "Unauthorized Test",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    async def provider_must_not_run(*_args, **_kwargs):
        raise AssertionError("authorization must stop before provider/model calls")

    def llm_must_not_initialize(*_args, **_kwargs):
        raise AssertionError("LLM must not initialize for unauthorized users")

    monkeypatch.setattr(server, "LlmChat", llm_must_not_initialize)
    monkeypatch.setattr(server, "build_chat_package", provider_must_not_run)
    monkeypatch.setattr(server, "build_workspace_snapshot", provider_must_not_run)
    monkeypatch.setattr(server.openai_client.audio.speech, "create", provider_must_not_run)
    monkeypatch.setattr(server.openai_client.audio.transcriptions, "create", provider_must_not_run)
    monkeypatch.setattr(gint, "credentials_for", provider_must_not_run)

    cases = [
        ("GET", "/api/auth/me", {}),
        ("POST", "/api/chat", {"json": {"message": "Merhaba", "conversation_id": "denied"}}),
        ("POST", "/api/voice/tts", {"data": {"text": "Merhaba Bora"}}),
        ("POST", "/api/voice/stt", {"files": {"file": ("audio.webm", b"fake", "audio/webm")}}),
        ("GET", "/api/workspace/snapshot", {}),
        ("GET", "/api/google/calendar/today", {}),
        ("GET", "/api/google/sheets", {}),
        ("GET", "/api/google/drive", {}),
        ("GET", "/api/google/doc", {}),
    ]

    async def exercise():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            for method, path, kwargs in cases:
                session_id = secrets.token_urlsafe(24)
                db.sessions.insert_one({
                    "session_id": session_id,
                    "user_id": user_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                signed = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(session_id)
                headers = {"Origin": os.environ["FRONTEND_URL"]}
                if method == "POST":
                    headers["X-CSRF-Token"] = _csrf_token(session_id)
                client.cookies.set("nova_session", signed)
                response = await client.request(
                    method,
                    path,
                    headers=headers,
                    **kwargs,
                )
                assert response.status_code == 403, (path, response.status_code, response.text)
                assert response.json()["detail"] == UNAUTHORIZED_MESSAGE
                assert db.sessions.find_one({"session_id": session_id}) is None

    try:
        asyncio.run(exercise())
        token_user_ids = {
            item["user_id"]
            for item in db.google_tokens.find({}, {"_id": 0, "user_id": 1})
            if item.get("user_id")
        }
        for token_user_id in token_user_ids:
            token_user = db.users.find_one({"id": token_user_id}, {"_id": 0, "email": 1})
            assert token_user and token_user.get("email", "").strip().casefold() == ALLOWED_USER_EMAIL
    finally:
        db.sessions.delete_many({"user_id": user_id})
        db.users.delete_one({"id": user_id})
        mongo.close()


def test_google_callback_blocks_non_allowlisted_state_user_before_token_exchange():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    user_id = f"TEST_callback_denied_{secrets.token_hex(6)}"
    state_value = f"state_{secrets.token_hex(10)}"

    db.users.insert_one({
        "id": user_id,
        "email": "intruder@example.com",
        "name": "Unauthorized Callback Test",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.google_oauth_states.insert_one({
        "state": state_value,
        "user_id": user_id,
        "code_verifier": "ignored-for-unauthorized",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        response = requests.get(
            f"{BASE_URL}/api/google/callback",
            params={"state": state_value, "code": "fake-code"},
            headers={"Origin": os.environ["FRONTEND_URL"]},
            timeout=30,
            allow_redirects=False,
        )
        assert response.status_code == 403
        assert response.json()["detail"] == UNAUTHORIZED_MESSAGE
        assert db.google_tokens.count_documents({"user_id": user_id}) == 0
        assert db.google_oauth_states.find_one({"state": state_value}) is None
    finally:
        db.google_oauth_states.delete_many({"user_id": user_id})
        db.google_tokens.delete_many({"user_id": user_id})
        db.users.delete_one({"id": user_id})
        mongo.close()