"""Real-data NOVA regression tests: chat date logic, weekly logic, and TTS voice contract."""
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
    """Create temporary signed nova_session for real Google-connected user."""
    user = mongo_db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1, "email": 1})
    assert user, f"Test user not found for email={TARGET_EMAIL}"

    token_doc = mongo_db.google_tokens.find_one({"user_id": user["id"]}, {"_id": 0, "user_id": 1})
    assert token_doc, "Google token not found for target user_id"

    sid = secrets.token_urlsafe(32)
    conversation_prefix = f"TEST_reg_{secrets.token_hex(4)}"
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-nova-regression-real",
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
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    return s


def chat_once(auth_client, conversation_id: str, message: str):
    return auth_client.post(
        f"{BASE_URL}/api/chat",
        json={"message": message, "conversation_id": conversation_id},
        timeout=90,
    )


# ---------- Real integration guard ----------
def test_google_status_is_connected(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/status", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["configured"] is True
    assert data["connected"] is True


# ---------- Chat: today program ----------
def test_chat_today_program_includes_concert_and_project_context(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_today"
    r = chat_once(auth_client, cid, "Nova bugün programımız ne?")
    assert r.status_code == 200, r.text
    answer = r.json().get("answer", "")
    folded = fold(answer)

    assert "bora bey" not in folded
    assert "sezon acilis konseri" in folded
    assert "20:00" in answer
    assert "grup karadus" in folded
    assert "farkindalik serisi" in folded


# ---------- Chat: 11 October wedding plan ----------
def test_chat_oct11_wedding_schedule_and_location(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_oct11"
    r = chat_once(auth_client, cid, "Nova 11 Ekim’deki nikâh programımı anlat.")
    assert r.status_code == 200, r.text
    answer = r.json().get("answer", "")
    folded = fold(answer)

    assert "villa verde mudanya" in folded
    assert "19:00" in answer
    assert ("20:00" in answer and "20:30" in answer)
    assert "gorunmuyor" not in folded
    assert "bilgi yok" not in folded


# ---------- Chat: weekly priorities ----------
def test_chat_weekly_top3_priorities_and_project_statuses(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_prio"
    r = chat_once(auth_client, cid, "Nova bu hafta en önemli 3 işim ne?")
    assert r.status_code == 200, r.text
    answer = r.json().get("answer", "")
    folded = fold(answer)

    assert "1." in answer and "2." in answer and "3." in answer
    assert "villa verde" in folded
    assert "konser" in folded
    assert "alanya" in folded
    assert ("bilet" in folded or "mekan" in folded)

    top3_part = fold(answer.split("\n\n")[0])
    assert "kasim antalya" not in top3_part

    assert "grup karadus" in folded and "bekliyor" in folded
    assert "farkindalik serisi" in folded and "aktif" in folded


# ---------- Chat: weekly Komagene routines ----------
def test_chat_weekly_komagene_past_vs_remaining(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_routines"
    r = chat_once(auth_client, cid, "Nova Komagene’de bu haftanın kalan rutinleri ne?")
    assert r.status_code == 200, r.text
    answer = r.json().get("answer", "")
    folded = fold(answer)

    assert "gecmis" in folded
    assert "kalan" in folded
    assert "sali" in folded and "siparis" in folded
    assert "carsamba" in folded and "sevkiyat" in folded
    assert "cuma" in folded and "siparis" in folded
    assert "cumartesi" in folded and "sevkiyat" in folded
    assert "cuma: sevkiyat" not in folded


# ---------- Date resolver regression ----------
def test_chat_oct25_wedding_found(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_oct25"
    r = chat_once(auth_client, cid, "Nova 25 Ekim nikâh programım nasıl?")
    assert r.status_code == 200, r.text
    answer = fold(r.json().get("answer", ""))

    assert "25 ekim" in answer
    assert "grand atilgan" in answer
    assert "eskisehir" in answer


def test_chat_next_saturday_resolves_expected_date(auth_client, temp_real_user_session):
    cid = f"{temp_real_user_session['conversation_prefix']}_next_sat"
    r = chat_once(auth_client, cid, "Nova gelecek cumartesi programım ne?")
    assert r.status_code == 200, r.text
    answer = fold(r.json().get("answer", ""))

    assert "cumartesi" in answer
    assert "10 ekim" in answer


# ---------- TTS contract ----------
def test_tts_headers_model_contract_and_mp3(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/voice/tts",
        data={"text": "Bora, bugün planını netleştirelim."},
        timeout=120,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert r.headers.get("X-Nova-Voice") == "coral"
    assert r.headers.get("X-Nova-Voice-Style") == "female-warm-professional"
    assert len(r.content) > 5000
