"""Targeted real connector checks for Core Stabilization V3."""
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
    BASE_URL = next(line.split("=", 1)[1].strip().rstrip("/") for line in env_file if line.startswith("REACT_APP_BACKEND_URL="))


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("ı", "i").replace("İ", "I"))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


@pytest.fixture(scope="module")
def real_session():
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    user = db.users.find_one({"email": "yapayzekasanatcisi@gmail.com"}, {"_id": 0, "id": 1})
    assert user
    sid = "v3-real-" + secrets.token_urlsafe(18)
    prefix = "TEST_v3_real_" + secrets.token_hex(5)
    db.sessions.insert_one({"session_id": sid, "user_id": user["id"], "auth_version": 2, "created_at": datetime.now(timezone.utc).isoformat(), "source": "pytest-v3-real"})
    client = requests.Session()
    client.headers.update({"Origin": BASE_URL})
    client.cookies.set("nova_session", URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid))
    csrf = client.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    client.headers["X-CSRF-Token"] = csrf.json()["csrf_token"]
    yield {"client": client, "db": db, "user_id": user["id"], "prefix": prefix}
    db.sessions.delete_one({"session_id": sid})
    db.messages.delete_many({"user_id": user["id"], "conversation_id": {"$regex": f"^{re.escape(prefix)}"}})
    db.conversation_contexts.delete_many({"user_id": user["id"], "conversation_id": {"$regex": f"^{re.escape(prefix)}"}})
    mongo.close()


def chat(real_session, suffix: str, message: str, timeout: int = 240):
    response = real_session["client"].post(
        f"{BASE_URL}/api/chat",
        json={"message": message, "conversation_id": f"{real_session['prefix']}_{suffix}", "source": "text"},
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_real_capability_registry(real_session):
    response = real_session["client"].get(f"{BASE_URL}/api/capabilities", timeout=120)
    assert response.status_code == 200
    data = response.json()
    for capability in ("calendar.read", "sheets.read", "drive.read", "docs.read", "gemini_search"):
        assert data[capability]["available"] is True
    for capability in ("calendar.write", "sheets.write", "gmail.read"):
        assert data[capability]["available"] is False


def test_meta_never_loads_workspace(real_session):
    data = chat(real_session, "meta", "Şu anda seni test ediyorum.")
    assert data["intent"] == "meta" and data["data_source"] == "Conversation"


def test_birthday_planning_uses_memory_as_context(real_session):
    data = chat(real_session, "birthday_plan", "Tuğba'nın doğum günü için 15.000 TL bütçeyle 3 plan hazırla.")
    assert data["intent"] == "planning"
    assert "10 kasim" in fold(data["answer"])
    assert sum(1 for marker in ("1", "2", "3") if marker in data["answer"]) >= 2


def test_personal_tiyatral_work_uses_real_sources(real_session):
    data = chat(real_session, "personal_work", "Bana Tiyatral Nikâh iş listemi gönder.")
    assert data["intent"] == "personal_work"
    assert "Calendar" in data["data_source"] and "Sheets" in data["data_source"]
    assert "checklist" not in fold(data["answer"])


def test_exact_entity_web_search(real_session):
    data = chat(real_session, "entity_web", "İnternetten Bora Ünsal Yapay Zekâ Sanatçısı hakkında araştır.")
    assert data["intent"] == "web_search" and data["sources"]
    assert "bora" in fold(data["answer"])


def test_restaurant_external_world_override(real_session):
    data = chat(real_session, "restaurant", "Bu akşam Tuğba'yla Bursa'da güzel bir yerde yemek yiyelim. 3 yer bul.")
    assert data["intent"] == "restaurant_search" and data["sources"]
    assert "bende kayitli degil" not in fold(data["answer"])


def test_multi_option_travel_completion(real_session):
    data = chat(real_session, "travel_modes", "İstanbul'a günübirlik özel araç, otobüs ve deniz yolunu karşılaştır.")
    answer = fold(data["answer"])
    assert data["intent"] == "travel_search" and data["sources"]
    for item in ("ozel arac", "otobus", "deniz"):
        assert item in answer


def test_calendar_multi_source_read_and_dedupe(real_session):
    response = real_session["client"].get(f"{BASE_URL}/api/google/calendar/date?date_value=2026-10-11", timeout=90)
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert events
    assert all(event["calendar"] in {"NOVA ASİSTAN — Özel Takvim", "Tiyatral Nikâh", "primary"} for event in events)
    keys = {(event["title"], event["start"], event["end"], event.get("location")) for event in events}
    assert len(keys) == len(events)


def test_calendar_natural_answer_and_follow_up(real_session):
    first = chat(real_session, "calendar_context", "11 Ekim'de ne işim var?")
    assert "villa verde" in fold(first["answer"])
    assert "19:00" in first["answer"] and "20:00" in first["answer"]
    second = chat(real_session, "calendar_context", "Peki kaçta orada olmam gerekiyor?")
    assert second["intent"] == "conversation_context" and "19:00" in second["answer"]


def test_availability_uses_calendar_and_ignores_routine_rule(real_session):
    data = chat(real_session, "availability", "Yarın 20:00 civarı müsait miyim?")
    assert data["intent"] == "availability"
    assert "Calendar" in data["data_source"]
    assert "erisimim yok" not in fold(data["answer"])


def test_missing_event_recovery(real_session):
    data = chat(real_session, "missing_event", "22 Ekim'deki Tiyatral Nikâhımla ilgili bilgi ver.")
    assert data["intent"] == "calendar_date_query"
    assert "kayitli" in fold(data["answer"]) or "takvime eklenmemis" in fold(data["answer"])


def test_write_actions_are_truthful_and_do_not_pollute(real_session):
    db = real_session["db"]
    before = (db.events.count_documents({}), db.tasks.count_documents({}))
    cases = [
        ("calendar_write", "Yarın 20:00'ye NOVA Test Etkinliği ekle."),
        ("task_create", "Cuma 16:00'ya kadar Komagene siparişini görev olarak ekle."),
        ("task_complete", "Alanya bilet görevini tamamlandı olarak işaretle."),
    ]
    for suffix, message in cases:
        data = chat(real_session, suffix, message)
        result = data["action_result"]
        assert result and result["executed"] is False and result["verified"] is False
        assert not any(word in data["answer"] for word in ("Ekledim", "Tamamlandı olarak işaretledim", "Sildim"))
    after = (db.events.count_documents({}), db.tasks.count_documents({}))
    assert before == after


def test_drive_docs_sheet_and_gmail_routes(real_session):
    drive = chat(real_session, "drive", "Drive'daki NOVA ASİSTAN klasörümde hangi dosyalar var?")
    docs = chat(real_session, "docs", "Docs'taki NOVA ASİSTAN — ÇEKİRDEK KURALLAR VE RUTİNLER belgesinden Komagene kurallarını özetle.")
    sheets = chat(real_session, "projects", "NOVA İş Merkezi'ndeki Projeler sayfasından aktif projelerimi göster.")
    gmail = chat(real_session, "gmail", "Gmail'imde önemli mail var mı?")
    assert drive["intent"] == "drive_read" and drive["data_source"] == "Google Drive"
    assert docs["intent"] == "docs_read" and docs["data_source"] == "Google Docs"
    assert sheets["intent"] == "sheets_read" and "Projeler" in sheets["data_source"]
    assert gmail["intent"] == "gmail_read" and "aktif değil" in gmail["answer"]


def test_relative_tomorrow_briefing_is_not_today(real_session):
    data = chat(real_session, "tomorrow_brief", "Yarın için kısa brifing hazırla.")
    assert data["intent"] == "briefing"
    assert data["resolved_target_date"] == "2026-10-10"


def test_risk_briefing_uses_workspace(real_session):
    data = chat(real_session, "risk", "Önümüzdeki birkaç gün içinde kaçırma riskim olan önemli iş var mı?")
    assert data["intent"] == "briefing"
    assert "Workspace" in data["data_source"]


def test_provider_targeted_shopping(real_session):
    data = chat(real_session, "shopping", "50.000 TL'ye MediaMarkt ve Hepsiburada'dan 3 laptop bul.")
    assert data["intent"] == "shopping_search" and data["sources"]
    source_text = fold(" ".join(f"{item.get('title','')} {item.get('url','')}" for item in data["sources"]))
    assert "mediamarkt" in source_text or "hepsiburada" in source_text or "mediamarkt" in fold(data["answer"])