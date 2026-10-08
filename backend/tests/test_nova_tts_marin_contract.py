"""Independent NOVA marin TTS contract verification with temporary signed session."""
import os
import secrets
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
EXACT_TEXT = (
    "Günaydın Bora. Bugün saat yirmide Bursa Bölge Devlet Senfoni Orkestrası konserin var. "
    "Öncesinde tamamlaman gereken işleri de istersen birlikte kontrol edebiliriz."
)
OUTPUT_MP3 = "/app/test_reports/nova-marin-final.mp3"


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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-nova-tts-marin-contract",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)

    yield {"cookie": cookie, "sid": sid}

    mongo_db.sessions.delete_one({"session_id": sid})


@pytest.fixture
def auth_client(temp_real_user_session):
    s = requests.Session()
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    return s


# --- Voice contract: exact sentence + mandatory response headers + nontrivial audio.
def test_tts_marin_exact_sentence_contract_and_output(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/voice/tts",
        data={"text": EXACT_TEXT},
        timeout=120,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert r.headers.get("X-Nova-Voice") == "marin"
    assert r.headers.get("X-Nova-Voice-Speed") == "1.08"
    assert r.headers.get("X-Nova-Voice-Style") == "female-executive-assistant-natural-tr"
    assert len(r.content) > 5000

    with open(OUTPUT_MP3, "wb") as f:
        f.write(r.content)
