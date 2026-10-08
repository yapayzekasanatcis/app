"""Independent NOVA primary/fallback TTS contract verification."""
import os
import secrets
import sys
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient


sys.path.append("/app/backend")
import server as server_module


load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

TARGET_EMAIL = "yapayzekasanatcisi@gmail.com"
EXACT_TEXT = (
    "Günaydın Bora. Bugün saat yirmide Bursa Bölge Devlet Senfoni Orkestrası konserin var. "
    "Öncesinde tamamlaman gereken işleri de istersen birlikte kontrol edebiliriz."
)
OUTPUT_MP3 = "/app/test_reports/nova-primary-final.mp3"


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="session")
def temp_real_user_session(mongo_db):
    """Temporary signed nova_session for linked real user. Cleans only temp session."""
    user = mongo_db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1})
    assert user, f"Test user not found for email={TARGET_EMAIL}"

    token_doc = mongo_db.google_tokens.find_one({"user_id": user["id"]}, {"_id": 0, "user_id": 1})
    assert token_doc, "Google token not found for target user_id"

    sid = secrets.token_urlsafe(32)
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "auth_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-nova-tts-marin-contract",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)

    yield {"cookie": cookie, "sid": sid}

    mongo_db.sessions.delete_one({"session_id": sid})


@pytest.fixture
def auth_client(temp_real_user_session):
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    csrf = s.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    s.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    return s


# --- Voice contract: exact sentence + mandatory response headers + nontrivial audio.
def test_tts_primary_exact_sentence_contract_and_output(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/voice/tts",
        data={"text": EXACT_TEXT},
        timeout=120,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert r.headers.get("X-Nova-Voice") == "nova"
    assert r.headers.get("X-Nova-Voice-Primary") == "nova"
    assert r.headers.get("X-Nova-Voice-Fallback") == "marin"
    assert r.headers.get("X-Nova-Voice-Speed") == "1.09"
    assert r.headers.get("X-Nova-Voice-Style") == "female-executive-assistant-natural-tr"
    assert r.headers.get("X-Nova-TTS-Mode") == "single-request"
    assert len(r.content) > 5000

    with open(OUTPUT_MP3, "wb") as f:
        f.write(r.content)


# --- Unit-level normalization guard (test-only) ---
def test_prepare_tts_text_exact_transform_contract():
    raw = "Birinci cümle...\n\nİkinci cümle — devam; tamam."
    normalized = server_module.prepare_tts_text(raw)
    assert normalized == "Birinci cümle. İkinci cümle, devam, tamam."


class _FakeSpeechResponse:
    def __init__(self, content: bytes):
        self.content = content


class _RecorderSpeechAPI:
    def __init__(self, fail_primary_once: bool = False):
        self.fail_primary_once = fail_primary_once
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_primary_once and len(self.calls) == 1 and kwargs.get("voice") == "nova":
            raise RuntimeError("forced primary failure for fallback coverage")
        return _FakeSpeechResponse(b"ID3" + b"x" * 128)


class _FakeOpenAIClient:
    def __init__(self, recorder: _RecorderSpeechAPI):
        class _Audio:
            def __init__(self, speech):
                self.speech = speech

        self.audio = _Audio(recorder)


# --- Unit stub (TEST-ONLY): verify single-call success + fallback call order/inputs ---
def test_tts_call_contract_single_request_and_fallback(monkeypatch):
    async def _run():
        sample_raw = "Birinci cümle...\n\nİkinci cümle — devam; tamam."
        expected = "Birinci cümle. İkinci cümle, devam, tamam."

        # normal success path -> exactly one speech.create call with nova and full normalized input
        recorder_ok = _RecorderSpeechAPI(fail_primary_once=False)
        monkeypatch.setattr(server_module, "openai_client", _FakeOpenAIClient(recorder_ok))
        response_ok = await server_module.tts(text=sample_raw, user={"id": "test-user"})
        chunks_ok = [chunk async for chunk in response_ok.body_iterator]
        assert b"".join(chunks_ok).startswith(b"ID3")
        assert len(recorder_ok.calls) == 1
        assert recorder_ok.calls[0]["voice"] == "nova"
        assert recorder_ok.calls[0]["input"] == expected
        assert recorder_ok.calls[0]["instructions"] == server_module.NOVA_TTS_INSTRUCTIONS
        assert recorder_ok.calls[0]["speed"] == server_module.NOVA_TTS_SPEED

        # forced primary failure -> exactly two calls in order nova -> marin with same full input
        recorder_fail = _RecorderSpeechAPI(fail_primary_once=True)
        monkeypatch.setattr(server_module, "openai_client", _FakeOpenAIClient(recorder_fail))
        response_fail = await server_module.tts(text=sample_raw, user={"id": "test-user"})
        chunks_fail = [chunk async for chunk in response_fail.body_iterator]
        assert b"".join(chunks_fail).startswith(b"ID3")
        assert len(recorder_fail.calls) == 2
        assert recorder_fail.calls[0]["voice"] == "nova"
        assert recorder_fail.calls[1]["voice"] == "marin"
        assert recorder_fail.calls[0]["input"] == expected
        assert recorder_fail.calls[1]["input"] == expected
        assert recorder_fail.calls[0]["instructions"] == recorder_fail.calls[1]["instructions"] == server_module.NOVA_TTS_INSTRUCTIONS
        assert recorder_fail.calls[0]["speed"] == recorder_fail.calls[1]["speed"] == server_module.NOVA_TTS_SPEED

    asyncio.run(_run())
