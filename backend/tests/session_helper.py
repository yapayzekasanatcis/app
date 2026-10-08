"""Utility to create/delete temporary nova_session for real-user UI/API tests."""
import json
import os
import secrets
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from pymongo import MongoClient


load_dotenv("/app/backend/.env")

TARGET_EMAIL = "yapayzekasanatcisi@gmail.com"


def _db():
    client = MongoClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


def create_temp_session():
    db = _db()
    user = db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1, "email": 1})
    if not user:
        raise RuntimeError(f"user not found for email={TARGET_EMAIL}")

    token_doc = db.google_tokens.find_one({"user_id": user["id"]}, {"_id": 0, "user_id": 1})
    if not token_doc:
        raise RuntimeError("google_tokens not found for target user")

    sid = secrets.token_urlsafe(32)
    db.sessions.insert_one({
        "session_id": sid,
        "user_id": user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "ui-test-session-helper",
    })
    cookie = URLSafeTimedSerializer(os.environ["SESSION_SECRET"]).dumps(sid)
    print(json.dumps({"session_id": sid, "cookie": cookie, "user_id": user["id"]}))


def delete_temp_session(session_id: str):
    db = _db()
    db.sessions.delete_one({"session_id": session_id})
    print(json.dumps({"deleted": True, "session_id": session_id}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python session_helper.py create|delete <session_id>")
    action = sys.argv[1]
    if action == "create":
        create_temp_session()
    elif action == "delete":
        if len(sys.argv) < 3:
            raise SystemExit("Usage: python session_helper.py delete <session_id>")
        delete_temp_session(sys.argv[2])
    else:
        raise SystemExit("Unknown action")
