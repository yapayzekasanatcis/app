"""Cleanup helper: remove recent test prompt messages from default conversation."""
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv("/app/backend/.env")

TARGET_USER_ID = "106153980006385211736"
PROMPTS = [
    "Nova bugün programımız ne?",
    "Nova 11 Ekim’deki nikâh programımı anlat.",
    "Nova bu hafta en önemli 3 işim ne?",
    "Nova Komagene’de bu haftanın kalan rutinleri ne?",
]


def main():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    threshold = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    result = db.messages.delete_many({
        "user_id": TARGET_USER_ID,
        "conversation_id": "default",
        "role": "user",
        "content": {"$in": PROMPTS},
        "created_at": {"$gte": threshold},
    })
    print({"deleted_user_prompt_messages": result.deleted_count})


if __name__ == "__main__":
    main()
