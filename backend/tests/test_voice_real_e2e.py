"""Real voice E2E regression: TTS -> STT -> Chat(source=voice) with Google-backed data."""
import os
import re
import secrets
import unicodedata
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient


load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

TARGET_EMAIL = "yapayzekasanatcisi@gmail.com"


def fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.replace("ı", "i").replace("İ", "I"))
    lowered = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    return " ".join(lowered.split())


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="session")
def temp_real_user_session(mongo_db):
    """Auth/session fixture for real Google-connected account (no token mutation)."""
    user = mongo_db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1})
    assert user, f"Test user not found for email={TARGET_EMAIL}"

    token_doc = mongo_db.google_tokens.find_one({"user_id": user["id"]}, {"_id": 0, "user_id": 1})
    assert token_doc, "Google token not found for target user_id"

    sid = secrets.token_urlsafe(32)
    conversation_prefix = f"TEST_voice_{secrets.token_hex(4)}"
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-voice-real-e2e",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)

    yield {"user_id": user["id"], "cookie": cookie, "sid": sid, "conversation_prefix": conversation_prefix}

    mongo_db.sessions.delete_one({"session_id": sid})
    mongo_db.messages.delete_many({
        "user_id": user["id"],
        "conversation_id": {"$regex": f"^{re.escape(conversation_prefix)}"},
    })


@pytest.fixture
def auth_client(temp_real_user_session):
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    csrf = s.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    s.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    return s


# --- Voice E2E helper: produce TTS audio, transcribe with STT, then chat with source=voice.
def voice_roundtrip(auth_client, temp_real_user_session, phrase: str, suffix: str):
    tts = auth_client.post(
        f"{BASE_URL}/api/voice/tts",
        data={"text": phrase},
        timeout=120,
    )
    assert tts.status_code == 200, tts.text[:300]
    assert tts.headers.get("content-type", "").startswith("audio/mpeg")
    assert len(tts.content) > 1000

    stt = auth_client.post(
        f"{BASE_URL}/api/voice/stt",
        files={"file": ("command.mp3", tts.content, "audio/mpeg")},
        timeout=120,
    )
    assert stt.status_code == 200, stt.text
    text = stt.json().get("text", "")
    assert isinstance(text, str) and text.strip(), stt.text

    cid = f"{temp_real_user_session['conversation_prefix']}_{suffix}"
    chat = auth_client.post(
        f"{BASE_URL}/api/chat",
        json={"message": text, "conversation_id": cid, "source": "voice"},
        timeout=120,
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload.get("source") == "voice"
    assert isinstance(payload.get("answer", ""), str) and payload.get("answer", "").strip()
    return text, payload, cid


# --- Intent robustness for three mandatory voice commands and typo/noise in STT output.
def test_voice_briefing_command_intent_and_real_data(auth_client, temp_real_user_session):
    stt_text, payload, _cid = voice_roundtrip(
        auth_client,
        temp_real_user_session,
        "Nova, günün brifingini sesli oku.",
        "briefing",
    )
    assert payload.get("intent") == "briefing", stt_text

    answer = fold(payload["answer"])
    assert "8 ekim" in answer
    assert "konser" in answer
    assert "bora ai studyo" in answer
    assert "3 bekleyen is" in answer


def test_voice_briefing_matches_briefing_today_service(auth_client, temp_real_user_session):
    stt_text, payload, _cid = voice_roundtrip(
        auth_client,
        temp_real_user_session,
        "Nova, günün brifingini sesli oku.",
        "briefing_sync",
    )
    assert payload.get("intent") == "briefing", stt_text

    brief = auth_client.get(f"{BASE_URL}/api/briefing/today", timeout=60)
    assert brief.status_code == 200, brief.text
    briefing_text = brief.json().get("text", "")
    assert fold(payload.get("answer", "")) == fold(briefing_text)


def test_voice_today_schedule_typo_robust_intent_and_event(auth_client, temp_real_user_session):
    stt_text, payload, _cid = voice_roundtrip(
        auth_client,
        temp_real_user_session,
        "Nova, bugünkü programım ne?",
        "today",
    )
    assert payload.get("intent") == "today_schedule", stt_text
    answer = fold(payload["answer"])
    assert "20:00" in payload["answer"]
    assert "sezon acilis konseri" in answer


def test_voice_pending_tasks_reads_real_sheets_not_empty(auth_client, temp_real_user_session):
    stt_text, payload, _cid = voice_roundtrip(
        auth_client,
        temp_real_user_session,
        "Nova, bekleyen işlerimi oku.",
        "pending",
    )
    assert payload.get("intent") == "pending_tasks", stt_text

    answer = fold(payload["answer"])
    assert "bekleyen is yok" not in answer
    assert "alanya" in answer and "bilet" in answer
    assert "alanya" in answer and "mekan" in answer
    assert "antalya" in answer and "bilet" in answer


# --- Source dispatch consistency: text/voice to same /api/chat endpoint with source persistence.
def test_chat_source_persisted_for_voice_and_text(auth_client, temp_real_user_session, mongo_db):
    cid = f"{temp_real_user_session['conversation_prefix']}_source"

    voice = auth_client.post(
        f"{BASE_URL}/api/chat",
        json={"message": "Nova bekleyen işlerimi oku", "conversation_id": cid, "source": "voice"},
        timeout=120,
    )
    assert voice.status_code == 200, voice.text
    assert voice.json().get("source") == "voice"

    text = auth_client.post(
        f"{BASE_URL}/api/chat",
        json={"message": "Nova bugün programım ne", "conversation_id": cid, "source": "text"},
        timeout=120,
    )
    assert text.status_code == 200, text.text
    assert text.json().get("source") == "text"

    rows = list(mongo_db.messages.find(
        {"user_id": temp_real_user_session["user_id"], "conversation_id": cid},
        {"_id": 0, "role": 1, "source": 1, "content": 1},
    ))
    assert rows, "No persisted chat rows"
    user_sources = {row.get("source") for row in rows if row.get("role") == "user"}
    assert "voice" in user_sources and "text" in user_sources
