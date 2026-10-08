"""Real Google integration tests for NOVA ASİSTAN (calendar/sheets/drive/docs + log redaction)."""
import os
import secrets
import sys
from datetime import datetime, timezone
from urllib.parse import unquote

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
CALENDAR_NAME = "NOVA ASİSTAN — Özel Takvim"
EXPECTED_TITLE = "Sezon Açılış Konseri — Bursa Bölge Devlet Senfoni Orkestrası"
EXPECTED_LOCATION = "Merinos AKKM Osmangazi Salonu"
DRIVE_FOLDER_NAME = "NOVA ASİSTAN"
DOC_NAME = "NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler"
REQUIRED_DOC_HEADINGS = [
    "NOVA ASİSTAN — ÇEKİRDEK KURALLAR VE RUTİNLER",
    "AMAÇ",
    "TEMEL DAVRANIŞ",
]


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
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "auth_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "pytest-google-real-integration",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)

    yield {"user_id": user["id"], "cookie": cookie, "sid": sid}

    mongo_db.sessions.delete_one({"session_id": sid})


@pytest.fixture
def auth_client(temp_real_user_session):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Origin": BASE_URL})
    s.cookies.set("nova_session", temp_real_user_session["cookie"])
    csrf = s.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    s.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    return s


# ---------- Google status ----------
def test_google_status_configured_connected(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/status", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["configured"] is True
    assert data["connected"] is True

    payload_text = str(data)
    assert "client_secret" not in payload_text
    assert "refresh_token" not in payload_text
    assert "access_token" not in payload_text


# ---------- Google calendar date ----------
def test_google_calendar_date_returns_real_oct8_event(auth_client):
    r = auth_client.get(
        f"{BASE_URL}/api/google/calendar/date",
        params={"date_value": "2026-10-08"},
        timeout=45,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["date"] == "2026-10-08"
    assert isinstance(data["events"], list)

    target = None
    for event in data["events"]:
        if event.get("title") == EXPECTED_TITLE:
            target = event
            break

    assert target is not None, f"Expected event not found. Events: {data['events']}"
    assert target["calendar"] == CALENDAR_NAME
    assert target["start"].startswith("2026-10-08T20:00:00+03:00")
    assert target["end"].startswith("2026-10-08T22:00:00+03:00")
    assert EXPECTED_LOCATION in (target.get("location") or "")


# ---------- Google verify ----------
def test_google_verify_event_and_sheets_tabs(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/verify", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["calendar"]["event_found"] is True
    assert data["calendar"]["name"] == CALENDAR_NAME
    assert isinstance(data["calendar"]["events"], list)

    assert data["sheets"]["file_found"] is True
    for tab_name in ("İşler", "Projeler", "Rutinler"):
        assert tab_name in data["sheets"]["tabs"]
        tab_data = data["sheets"]["tabs"][tab_name]
        assert tab_data["readable"] is True
        assert isinstance(tab_data["row_count"], int)


# ---------- Google drive ----------
def test_google_drive_folder_and_core_doc_file_visible(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/drive", timeout=45)
    assert r.status_code == 200, r.text
    data = r.json()

    folder = data["folder"]
    assert folder["name"] == DRIVE_FOLDER_NAME
    assert isinstance(folder.get("id"), str) and len(folder["id"]) > 5

    files = data.get("files")
    assert isinstance(files, list)
    assert any((f.get("name") or "") == DOC_NAME for f in files), f"Drive files: {[f.get('name') for f in files]}"


# ---------- Google docs ----------
def test_google_doc_reads_real_text_and_required_headings(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/doc", timeout=45)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["name"] == DOC_NAME
    assert isinstance(data.get("text"), str)
    assert len(data["text"].strip()) > 0

    headings = data.get("headings")
    assert isinstance(headings, list)
    heading_set = {h.strip() for h in headings if isinstance(h, str)}
    for required in REQUIRED_DOC_HEADINGS:
        assert required in heading_set, f"Missing heading '{required}' in {headings}"


def test_google_verify_includes_drive_docs_flags_and_required_headings(auth_client):
    r = auth_client.get(f"{BASE_URL}/api/google/verify", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["drive"]["name"] == DRIVE_FOLDER_NAME
    assert data["drive"]["folder_found"] is True
    assert isinstance(data["drive"].get("file_count"), int)
    assert DOC_NAME in data["drive"].get("files", [])

    assert data["docs"]["name"] == DOC_NAME
    assert data["docs"]["document_found"] is True
    assert data["docs"]["content_readable"] is True
    assert isinstance(data["docs"].get("content_length"), int)
    assert data["docs"]["content_length"] > 0

    verify_headings = data["docs"].get("headings", [])
    assert isinstance(verify_headings, list)
    for required in REQUIRED_DOC_HEADINGS:
        assert required in verify_headings, f"Missing verify heading '{required}' in {verify_headings}"


# ---------- OAuth callback access-log redaction ----------
def test_callback_access_log_filter_redacts_sensitive_query_fields():
    sys.path.append("/app/backend")
    from google_integration import OAuthAccessLogFilter
    import logging

    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:12345",
            "GET",
            "/api/google/callback?code=abc123&state=st999&foo=ok&client_secret=secretv&access_token=tokv",
            "1.1",
            307,
        ),
        exc_info=None,
    )

    flt = OAuthAccessLogFilter()
    assert flt.filter(record) is True

    path_after = unquote(record.args[2])
    assert "code=[REDACTED]" in path_after
    assert "state=[REDACTED]" in path_after
    assert "client_secret=[REDACTED]" in path_after
    assert "access_token=[REDACTED]" in path_after
    assert "foo=ok" in path_after
    assert "abc123" not in path_after
    assert "st999" not in path_after
    assert "secretv" not in path_after
    assert "tokv" not in path_after
