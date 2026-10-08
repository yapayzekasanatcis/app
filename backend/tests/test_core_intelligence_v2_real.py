"""Required real-data acceptance suite for NOVA Core Intelligence V2."""
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
with open("/app/frontend/.env", encoding="utf-8") as env_file:
    BASE_URL = next(
        line.split("=", 1)[1].strip().rstrip("/")
        for line in env_file
        if line.startswith("REACT_APP_BACKEND_URL=")
    )


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("ı", "i").replace("İ", "I"))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


@pytest.fixture(scope="module")
def core_session():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    user = db.users.find_one({"email": "yapayzekasanatcisi@gmail.com"}, {"_id": 0, "id": 1})
    assert user
    sid = "core-v2-real-" + secrets.token_urlsafe(18)
    prefix = "TEST_core_v2_real_" + secrets.token_hex(5)
    db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "auth_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-core-intelligence-v2-real",
    })
    client = requests.Session()
    client.headers.update({"Origin": BASE_URL})
    client.cookies.set("nova_session", URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid))
    csrf = client.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    client.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    yield {"client": client, "db": db, "user_id": user["id"], "prefix": prefix}
    db.sessions.delete_one({"session_id": sid})
    db.messages.delete_many({"user_id": user["id"], "conversation_id": {"$regex": f"^{re.escape(prefix)}"}})
    db.conversation_contexts.delete_many({"user_id": user["id"], "conversation_id": {"$regex": f"^{re.escape(prefix)}"}})
    mongo.close()


def chat(core_session, suffix: str, message: str, source: str = "text", timeout: int = 180):
    response = core_session["client"].post(
        f"{BASE_URL}/api/chat",
        json={"message": message, "conversation_id": f"{core_session['prefix']}_{suffix}", "source": source},
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_01_today_program_calendar(core_session):
    data = chat(core_session, "today", "Bugün programım ne?")
    assert data["intent"] == "today_schedule"
    assert "Calendar" in data["data_source"]


def test_02_oct11_villa_verde_calendar(core_session):
    data = chat(core_session, "oct11", "11 Ekim'de ne işim var?")
    assert data["intent"] == "calendar_date_query"
    assert "villa verde" in fold(data["answer"]) and "mudanya" in fold(data["answer"])


@pytest.mark.parametrize(
    "suffix, question, expected",
    [
        ("tugba", "Tuğba'nın doğum günü?", "10 Kasım 1990"),
        ("atakan", "Atakan'ın doğum günü?", "11 Ocak"),
        ("bora", "Benim doğum günüm?", "12 Mayıs 1978"),
        ("anne", "Annemin doğum günü?", "13 Temmuz"),
        ("tolga", "Tolga'nın doğum günü?", "29 Temmuz"),
    ],
)
def test_03_to_07_family_memory(core_session, suffix, question, expected):
    data = chat(core_session, suffix, question)
    assert data["data_source"] == "Personal Memory"
    assert expected in data["answer"]


def test_08_soup_memory(core_session):
    data = chat(core_session, "soups", "Ben hangi çorbaları severim?")
    answer = fold(data["answer"])
    assert data["data_source"] == "Personal Memory"
    assert all(item in answer for item in ("kasarli domates", "mercimek", "ezogelin"))


def test_09_vegetable_rule(core_session):
    data = chat(core_session, "vegetable", "Sebze yemeği öner.")
    assert data["data_source"] == "Personal Memory"
    assert "önermiyorum" in data["answer"]


def test_10_travel_preference(core_session):
    data = chat(core_session, "travel_pref", "İstanbul'a genelde nasıl gitmek isterim?")
    assert data["data_source"] == "Personal Memory"
    assert "özel araç" in data["answer"]


def test_11_unknown_personal_fallback(core_session):
    data = chat(core_session, "unknown", "Tuğba'nın ayakkabı numarası?")
    assert data["data_source"] == "Unknown Fallback"
    assert data["answer"].startswith("Bu bilgi bende kayıtlı değil, Bora.")


def test_12_general_knowledge(core_session):
    data = chat(core_session, "general", "Türkiye'nin başkenti?")
    assert data["data_source"] == "General LLM"
    assert "ankara" in fold(data["answer"])


def test_13_open_soup_calendar_and_live_web(core_session):
    data = chat(core_session, "open_soup", "Konserden sonra açık çorbacı bul.")
    assert data["intent"] == "web_search"
    assert data["data_source"] == "Calendar + Web Search"
    assert data["sources"]
    assert not data["answer"].startswith("Şu anda canlı arama sonucu alamadım")


def test_14_calendar_follow_up_context(core_session):
    first = chat(core_session, "followup", "11 Ekim'de Villa Verde etkinliğim nerede?")
    assert "villa verde" in fold(first["answer"])
    second = chat(core_session, "followup", "Peki kaçta?")
    assert second["data_source"] == "Conversation Context"
    assert "19:00" in second["answer"]


def test_15_pending_tasks_workspace(core_session):
    data = chat(core_session, "pending", "Bekleyen işlerimi söyle.")
    assert data["data_source"] == "Workspace"
    assert "bekleyen is" in fold(data["answer"])


def test_16_komagene_routines(core_session):
    data = chat(core_session, "routines", "Bu hafta Komagene'de ne yapmam gerekiyor?")
    assert data["data_source"] == "Workspace Routines"
    assert "komagene" in fold(data["answer"])


def test_17_alanya_travel_calendar_web_profile(core_session):
    data = chat(core_session, "alanya", "17 Ekim Alanya için ulaşımımı araştır.", timeout=240)
    assert data["intent"] == "travel_search"
    assert data["data_source"] == "Calendar/Workspace + Web Search + Travel Profile"
    assert data["sources"]
    assert "alanya" in fold(data["answer"])


def test_18_istanbul_night_car_route(core_session):
    data = chat(core_session, "istanbul_car", "İstanbul'a arabayla gidiyorum; dönüşüm gece. En mantıklı rota ne?", timeout=240)
    answer = fold(data["answer"])
    assert data["intent"] == "travel_search"
    assert data["sources"]
    assert "feribot" in answer or "kopru" in answer


def voice_input(core_session, suffix: str, phrase: str):
    tts = core_session["client"].post(f"{BASE_URL}/api/voice/tts", data={"text": phrase}, timeout=120)
    assert tts.status_code == 200, tts.text[:300]
    stt = core_session["client"].post(
        f"{BASE_URL}/api/voice/stt",
        files={"file": ("command.mp3", tts.content, "audio/mpeg")},
        timeout=120,
    )
    assert stt.status_code == 200, stt.text
    text = stt.json()["text"]
    data = chat(core_session, suffix, text, source="voice", timeout=180)
    data["transcript"] = text
    return data


def test_19_voice_tugba_memory(core_session):
    data = voice_input(core_session, "voice_tugba", "Tuğba'nın doğum günü ne zaman?")
    assert data["source"] == "voice", data["transcript"]
    assert data["data_source"] == "Personal Memory", data["transcript"]
    assert "10 Kasım 1990" in data["answer"]


def test_20_voice_today_calendar(core_session):
    data = voice_input(core_session, "voice_today", "Bugün programım ne?")
    assert data["source"] == "voice", data["transcript"]
    assert data["intent"] == "today_schedule", data["transcript"]


def test_21_voice_pending_workspace(core_session):
    data = voice_input(core_session, "voice_pending", "Bekleyen işlerimi söyle.")
    assert data["source"] == "voice"
    assert data["intent"] == "pending_tasks"