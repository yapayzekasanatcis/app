"""Pytest fixtures for NOVA ASİSTAN backend tests."""
import os
import secrets
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient

load_dotenv('/app/backend/.env')

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/') if os.environ.get('REACT_APP_BACKEND_URL') else None
if not BASE_URL:
    # fallback from frontend env
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                break

TEST_USER_ID = "TEST_bora"
ALLOWED_USER_EMAIL = os.environ["ALLOWED_USER_EMAIL"]


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ['MONGO_URL'])
    return client[os.environ['DB_NAME']]


@pytest.fixture(scope="session")
def test_session_cookie(mongo_db):
    """Create a test user + session in Mongo and return a signed cookie."""
    mongo_db.users.update_one(
        {"id": TEST_USER_ID},
        {"$set": {
            "id": TEST_USER_ID,
            "email": ALLOWED_USER_EMAIL,
            "name": "Bora Test",
            "picture": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    sid = secrets.token_urlsafe(32)
    mongo_db.sessions.insert_one({
        "session_id": sid,
        "user_id": TEST_USER_ID,
        "auth_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    token = URLSafeTimedSerializer(os.environ['SESSION_SECRET']).dumps(sid)
    yield token
    # cleanup
    mongo_db.sessions.delete_one({"session_id": sid})


@pytest.fixture
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def auth_client(test_session_cookie):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Origin": BASE_URL})
    s.cookies.set("nova_session", test_session_cookie)
    csrf = s.get(f"{BASE_URL}/api/auth/csrf", timeout=30)
    assert csrf.status_code == 200, csrf.text
    s.headers.update({"X-CSRF-Token": csrf.json()["csrf_token"]})
    return s


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(mongo_db):
    yield
    # Teardown: delete all data for test user
    for coll in ("tasks", "notes", "events", "messages", "sessions", "users"):
        mongo_db[coll].delete_many({"user_id": TEST_USER_ID})
    mongo_db.users.delete_many({"id": TEST_USER_ID})
