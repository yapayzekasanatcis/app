"""Real Google Workspace snapshot assertions for shared page data layer."""
import os
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
EXPECTED_CONCERT = "Sezon Açılış Konseri — Bursa Bölge Devlet Senfoni Orkestrası"
EXPECTED_WEDDING = "Tiyatral Nikâh — Villa Verde Mudanya"


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").replace("ı", "i").replace("İ", "I"))
    lowered = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    return " ".join(lowered.split())


def includes_text(items: list, expected: str) -> bool:
    expected_folded = fold(expected)
    return any(expected_folded in fold(item.get("title", "")) for item in items)


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="session")
def temp_real_user_session(mongo_db):
    """Temporary signed nova_session for linked real Google user."""
    user = mongo_db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1, "email": 1})
    assert user, f"Test user not found for email={TARGET_EMAIL}"

    token_doc = mongo_db.google_tokens.find_one({"user_id": user["id"]}, {"_id": 0, "user_id": 1})
    assert token_doc, "Google token not found for target user_id"

    sid = secrets.token_urlsafe(32)
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-workspace-snapshot-real",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)

    yield {"user_id": user["id"], "cookie": cookie, "sid": sid}

    mongo_db.sessions.delete_one({"session_id": sid})


@pytest.fixture
def auth_client(temp_real_user_session):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    return s


# Shared snapshot contract verification for all workspace pages
def test_workspace_snapshot_real_contract(auth_client):
    response = auth_client.get(f"{BASE_URL}/api/workspace/snapshot", timeout=90)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["sources"]["calendar"]["connected"] is True
    assert data["sources"]["sheets"]["connected"] is True

    today_events = data.get("today_events", [])
    week_events = data.get("week_events", [])
    all_events = data.get("calendar_events", [])

    concert = next((event for event in today_events if fold(event.get("title", "")) == fold(EXPECTED_CONCERT)), None)
    assert concert is not None, f"today_events missing concert: {today_events}"
    assert concert.get("start_time", "").startswith("2026-10-08T20:00")

    assert includes_text(week_events, EXPECTED_CONCERT), f"week_events missing concert: {week_events}"
    assert includes_text(week_events, EXPECTED_WEDDING), f"week_events missing Villa Verde wedding: {week_events}"

    pending_tasks = data.get("pending_tasks", [])
    pending_blob = fold(" ".join(task.get("title", "") for task in pending_tasks))
    assert "alanya" in pending_blob and "bilet" in pending_blob
    assert "alanya" in pending_blob and "mekan" in pending_blob
    assert "antalya" in pending_blob and "bilet" in pending_blob

    priorities = data.get("priorities", [])
    assert len(priorities) > 0
    assert any(item.get("source") == "Google Sheets · İşler" for item in priorities)
    assert any(item.get("source") == "Google Sheets · Projeler" for item in priorities)

    komagene = data.get("komagene", {}).get("routines", [])
    komagene_blob = fold(" ".join(item.get("title", "") for item in komagene))
    assert "siparis" in komagene_blob
    assert "sevkiyat" in komagene_blob

    tiyatral_events = data.get("tiyatral", {}).get("events", [])
    tiyatral_tasks = data.get("tiyatral", {}).get("tasks", [])
    assert includes_text(tiyatral_events, EXPECTED_WEDDING)
    tiyatral_blob = fold(" ".join(item.get("title", "") for item in tiyatral_tasks))
    assert "alanya" in tiyatral_blob and "antalya" in tiyatral_blob

    projects = data.get("bora_ai", {}).get("projects", [])
    project_map = {fold(item.get("title", "")): fold(item.get("status", "")) for item in projects}
    assert project_map.get(fold("Grup Karadüş — Kadına Şiddet Şarkısı Klibi")) == fold("Bekliyor")
    assert project_map.get(fold("Farkındalık Serisi — Kadına Şiddet")) == fold("Aktif")

    all_event_ids = {item.get("id") for item in all_events}
    assert all(item.get("id") in all_event_ids for item in today_events)
    assert all(item.get("id") in all_event_ids for item in week_events)
    assert all(task.get("id", "").startswith("sheet-task-") for task in pending_tasks)
