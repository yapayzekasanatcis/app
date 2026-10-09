"""Only the requested real-provider acceptance checks for the final hotfix."""
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
def hotfix_session():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    user = db.users.find_one({"email": "yapayzekasanatcisi@gmail.com"}, {"_id": 0, "id": 1})
    assert user
    sid = "final-hotfix-" + secrets.token_urlsafe(18)
    prefix = "TEST_final_hotfix_" + secrets.token_hex(5)
    db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "auth_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-final-hotfix-real",
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


def chat(hotfix_session, suffix: str, message: str, timeout: int = 240):
    response = hotfix_session["client"].post(
        f"{BASE_URL}/api/chat",
        json={"message": message, "conversation_id": f"{hotfix_session['prefix']}_{suffix}", "source": "text"},
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "http" not in data["answer"].lower()
    return data


def assert_live(data, intent):
    assert data["intent"] == intent
    assert data["sources"], data["answer"]
    assert not data["answer"].startswith("Bu bilgiyi canlı kaynaktan doğrulayamadım")
    assert all(placeholder not in data["answer"] for placeholder in ("Otel A", "Otel B", "Restoran A", "Restoran B"))


def test_01_eskisehir_two_day_travel(hotfix_session):
    data = chat(hotfix_session, "eskisehir", "Bu hafta sonu Tuğba'yla Eskişehir'e iki günlük gezi planla.")
    assert_live(data, "travel_search")
    assert "eskisehir" in fold(data["answer"])


def test_02_yalova_termal_real_hotels(hotfix_session):
    data = chat(hotfix_session, "yalova_hotel", "Yalova Termal'de iki kişilik otel araştır.")
    assert_live(data, "hotel_search")
    assert "hotel" in data["data_source"].lower()


def test_03_alanya_obilet_priority(hotfix_session):
    data = chat(hotfix_session, "alanya_obilet", "17 Ekim Alanya için Obilet'ten gidiş dönüş otobüs araştır.")
    assert_live(data, "travel_search")
    source_text = fold(" ".join(f"{item.get('title', '')} {item.get('url', '')}" for item in data["sources"]))
    assert "obilet" in source_text or "obilet" in fold(data["answer"])


def test_04_antalya_pegasus_and_thy(hotfix_session):
    data = chat(hotfix_session, "antalya_flight", "Antalya için Pegasus ve THY uçuşlarını araştır.")
    assert_live(data, "travel_search")
    answer = fold(data["answer"])
    assert "pegasus" in answer
    assert "thy" in answer or "turk hava" in answer or "ajet" in answer


def test_05_bursa_dinner_real_restaurants_no_profile_dump(hotfix_session):
    data = chat(hotfix_session, "dinner", "Bu akşam Bursa'da yemek yiyelim.")
    assert_live(data, "restaurant_search")
    answer = fold(data["answer"])
    assert "bora sebze" not in answer and "kisisel tercih" not in answer


def test_06_late_soup_real_open_place(hotfix_session):
    data = chat(hotfix_session, "late_soup", "23:00 sonrası mercimek/kaşarlı domates çorbası bul.")
    assert_live(data, "restaurant_search")
    assert "corba" in fold(data["answer"])


def test_07_cinetime_first_live_sessions(hotfix_session):
    data = chat(hotfix_session, "cinema", "Yarın Tuğba'yla sinemaya gidelim.")
    assert_live(data, "cinema_search")
    combined = fold(data["answer"] + " " + " ".join(item.get("title", "") for item in data["sources"]))
    assert "cinetime" in combined or "ozdilek" in combined


def test_08_weekend_events_not_routine(hotfix_session):
    data = chat(hotfix_session, "events", "Bu hafta sonu Bursa'da konser/tiyatro araştır.")
    assert_live(data, "event_search")
    assert "routine" not in data["data_source"].lower()


def test_09_five_hour_bursa_leisure_plan(hotfix_session):
    data = chat(hotfix_session, "leisure", "Yarın Bursa'da 5 saatlik plan yap.")
    assert_live(data, "leisure_search")
    assert "bursa" in fold(data["answer"])


def test_10_event_follow_up_context(hotfix_session):
    first = chat(hotfix_session, "followup", "11 Ekim'de ne işim var?")
    assert "villa verde" in fold(first["answer"])
    second = chat(hotfix_session, "followup", "Peki kaçta?")
    assert second["intent"] == "conversation_context"
    assert "19:00" in second["answer"]


def tts_roundtrip(hotfix_session, text: str) -> str:
    tts = hotfix_session["client"].post(f"{BASE_URL}/api/voice/tts", data={"text": text}, timeout=120)
    assert tts.status_code == 200, tts.text[:300]
    stt = hotfix_session["client"].post(
        f"{BASE_URL}/api/voice/stt",
        files={"file": ("tts.mp3", tts.content, "audio/mpeg")},
        timeout=120,
    )
    assert stt.status_code == 200, stt.text
    return stt.json()["text"]


def test_11_web_answer_tts_omits_sources(hotfix_session):
    transcript = fold(tts_roundtrip(hotfix_session, "İki gerçek seçenek buldum. Kaynaklar: https://example.com/redirect/path"))
    assert "http" not in transcript and "example" not in transcript and "kaynaklar" not in transcript


def test_12_tts_reads_2000_as_turkish_clock(hotfix_session):
    transcript = fold(tts_roundtrip(hotfix_session, "Etkinlik 20:00'de başlıyor."))
    assert "yirmi" in transcript or "20" in transcript
    assert "sifir sifir" not in transcript and "zero zero" not in transcript