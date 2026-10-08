"""Backend tests for NOVA ASİSTAN API."""
import io
import pytest


# ---------- Root ----------
def test_root(anon_client, base_url):
    r = anon_client.get(f"{base_url}/api/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "online"
    assert "NOVA" in data.get("message", "")


# ---------- Auth: unauthenticated ----------
@pytest.mark.parametrize("path,method", [
    ("/api/auth/me", "get"),
    ("/api/tasks", "get"),
    ("/api/notes", "get"),
    ("/api/events", "get"),
    ("/api/briefing/today", "get"),
    ("/api/chat", "post"),
    ("/api/voice/tts", "post"),
    ("/api/voice/stt", "post"),
])
def test_endpoints_require_auth(anon_client, base_url, path, method):
    r = getattr(anon_client, method)(f"{base_url}{path}")
    assert r.status_code == 401, f"{path} returned {r.status_code}"


def test_auth_session_invalid(anon_client, base_url):
    r = anon_client.post(f"{base_url}/api/auth/session", json={"session_id": "invalid-xxxx"})
    assert r.status_code == 401


# ---------- Auth: with cookie ----------
def test_auth_me_with_cookie(auth_client, base_url):
    r = auth_client.get(f"{base_url}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "TEST_bora"
    assert data["email"] == "test_bora@example.com"
    assert data["name"] == "Bora Test"


# ---------- Tasks CRUD ----------
class TestTasks:
    def test_task_crud_flow(self, auth_client, base_url):
        # Create
        payload = {"title": "TEST_Task1", "priority": "yuksek", "context": "kisisel"}
        r = auth_client.post(f"{base_url}/api/tasks", json=payload)
        assert r.status_code == 200, r.text
        task = r.json()
        assert task["title"] == "TEST_Task1"
        assert task["user_id"] == "TEST_bora"
        assert task["completed"] is False
        tid = task["id"]

        # List
        r = auth_client.get(f"{base_url}/api/tasks")
        assert r.status_code == 200
        assert any(t["id"] == tid for t in r.json())

        # Patch - mark priority
        r = auth_client.patch(f"{base_url}/api/tasks/{tid}", json={"is_priority": True})
        assert r.status_code == 200
        assert r.json()["is_priority"] is True

        # Patch - complete
        r = auth_client.patch(f"{base_url}/api/tasks/{tid}", json={"completed": True})
        assert r.status_code == 200
        updated = r.json()
        assert updated["completed"] is True
        assert updated.get("completed_at")

        # Delete
        r = auth_client.delete(f"{base_url}/api/tasks/{tid}")
        assert r.status_code == 200

        # Verify gone
        r = auth_client.delete(f"{base_url}/api/tasks/{tid}")
        assert r.status_code == 404

    def test_task_context_filtering(self, auth_client, base_url):
        contexts = ["kisisel", "komagene", "tiyatral-nikah", "bora-ai-studyo"]
        created = []
        for ctx in contexts:
            r = auth_client.post(f"{base_url}/api/tasks", json={"title": f"TEST_ctx_{ctx}", "context": ctx})
            assert r.status_code == 200
            created.append(r.json()["id"])

        for ctx in contexts:
            r = auth_client.get(f"{base_url}/api/tasks", params={"context": ctx})
            assert r.status_code == 200
            rows = r.json()
            assert all(t["context"] == ctx for t in rows), f"filter failed for {ctx}"
            assert any(t["title"] == f"TEST_ctx_{ctx}" for t in rows)

        # cleanup
        for tid in created:
            auth_client.delete(f"{base_url}/api/tasks/{tid}")


# ---------- Notes CRUD ----------
class TestNotes:
    def test_note_crud(self, auth_client, base_url):
        r = auth_client.post(f"{base_url}/api/notes", json={"title": "TEST_Note", "content": "Deneme içerik", "category": "fikir", "context": "komagene"})
        assert r.status_code == 200
        note = r.json()
        assert note["content"] == "Deneme içerik"
        assert note["user_id"] == "TEST_bora"
        nid = note["id"]

        r = auth_client.get(f"{base_url}/api/notes")
        assert r.status_code == 200
        assert any(n["id"] == nid for n in r.json())

        # context filter
        r = auth_client.get(f"{base_url}/api/notes", params={"context": "komagene"})
        assert r.status_code == 200
        assert all(n["context"] == "komagene" for n in r.json())

        r = auth_client.delete(f"{base_url}/api/notes/{nid}")
        assert r.status_code == 200
        r = auth_client.delete(f"{base_url}/api/notes/{nid}")
        assert r.status_code == 404


# ---------- Events CRUD ----------
class TestEvents:
    def test_event_crud(self, auth_client, base_url):
        payload = {
            "title": "TEST_Event",
            "start_time": "2026-01-15T10:00:00",
            "end_time": "2026-01-15T11:00:00",
            "location": "Komagene",
            "context": "komagene",
        }
        r = auth_client.post(f"{base_url}/api/events", json=payload)
        assert r.status_code == 200, r.text
        ev = r.json()
        eid = ev["id"]

        # Range filter
        r = auth_client.get(f"{base_url}/api/events", params={"start": "2026-01-01", "end": "2026-01-31"})
        assert r.status_code == 200
        assert any(e["id"] == eid for e in r.json())

        # Out of range
        r = auth_client.get(f"{base_url}/api/events", params={"start": "2027-01-01", "end": "2027-01-31"})
        assert r.status_code == 200
        assert not any(e["id"] == eid for e in r.json())

        r = auth_client.delete(f"{base_url}/api/events/{eid}")
        assert r.status_code == 200


# ---------- Chat ----------
class TestChat:
    def test_chat_turkish(self, auth_client, base_url, mongo_db):
        r = auth_client.post(
            f"{base_url}/api/chat",
            json={"message": "Merhaba NOVA, bugün nasılsın?", "conversation_id": "TEST_conv"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "answer" in data
        assert isinstance(data["answer"], str) and len(data["answer"]) > 0

        # Persistence check
        msgs = list(mongo_db.messages.find({"user_id": "TEST_bora", "conversation_id": "TEST_conv"}))
        assert len(msgs) >= 2
        roles = {m["role"] for m in msgs}
        assert "user" in roles and "assistant" in roles


# ---------- Briefing ----------
class TestBriefing:
    def test_briefing_today(self, auth_client, base_url):
        r = auth_client.get(f"{base_url}/api/briefing/today", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("text", "events", "priorities", "pending_count", "date"):
            assert key in data, f"missing {key}"
        assert isinstance(data["events"], list)
        assert isinstance(data["priorities"], list)
        assert isinstance(data["pending_count"], int)
        assert isinstance(data["text"], str) and len(data["text"]) > 0


# ---------- TTS ----------
class TestTTS:
    def test_tts_returns_mp3(self, auth_client, base_url):
        r = auth_client.post(
            f"{base_url}/api/voice/tts",
            data={"text": "Merhaba Bora, bugün güzel bir gün."},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60,
        )
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("audio/mpeg")
        assert len(r.content) > 500  # non-trivial mp3

    def test_tts_empty_rejected(self, auth_client, base_url):
        r = auth_client.post(
            f"{base_url}/api/voice/tts",
            data={"text": "   "},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 400


# ---------- Logout ----------
def test_logout_clears_session(base_url, mongo_db):
    """Logout should delete session and clear cookie (separate session from main test cookie)."""
    import secrets as _s
    from datetime import datetime, timezone
    from itsdangerous import URLSafeTimedSerializer
    import os, requests

    sid = _s.token_urlsafe(32)
    mongo_db.users.update_one(
        {"id": "TEST_bora_logout"},
        {"$set": {"id": "TEST_bora_logout", "email": "lo@test.com", "name": "LO"}},
        upsert=True,
    )
    mongo_db.sessions.insert_one({"session_id": sid, "user_id": "TEST_bora_logout", "created_at": datetime.now(timezone.utc).isoformat()})
    token = URLSafeTimedSerializer(os.environ['SESSION_SECRET']).dumps(sid)

    s = requests.Session()
    s.cookies.set("nova_session", token)
    r = s.post(f"{base_url}/api/auth/logout")
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # Session row deleted
    assert mongo_db.sessions.find_one({"session_id": sid}) is None

    # cleanup user
    mongo_db.users.delete_one({"id": "TEST_bora_logout"})
