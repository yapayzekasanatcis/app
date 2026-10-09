"""Per-user and per-conversation short follow-up context."""
from datetime import datetime, timezone

from date_resolver import fold_turkish


def _is_follow_up(message: str) -> bool:
    folded = fold_turkish(message).strip(" ,.!?")
    return (
        folded.startswith(("peki", "ya ", "orada", "onda", "daha "))
        or folded in {"kacta", "nerede", "neden", "ne kadar", "hangisi", "nasil"}
        or "kacta orada" in folded
    )


def _event_time(event: dict) -> str:
    start = event.get("start") or event.get("start_time") or ""
    return start[11:16] if "T" in start else "tüm gün"


def resolve_follow_up(message: str, context: dict | None) -> dict | None:
    if not context or not _is_follow_up(message):
        return None
    folded = fold_turkish(message)
    events = context.get("events") or []
    event = events[0] if events else None
    if event and "kacta" in folded:
        time_value = _event_time(event)
        location = event.get("location", "")
        if "orada" in folded and location:
            return {"intent": "conversation_context", "reply": f"Bora, program kaydına göre {time_value}'de {location}'da olmalısın."}
        return {"intent": "conversation_context", "reply": f"Bora, {time_value}'de başlıyor."}
    if event and "nerede" in folded:
        location = event.get("location")
        return {
            "intent": "conversation_context",
            "reply": f"Bora, {location}." if location else "Bu etkinliğin konumu takvim kaydında belirtilmemiş, Bora.",
        }
    return {
        "intent": context.get("intent", "general"),
        "reply": None,
        "prior_context": f"Önceki soru: {context.get('last_question', '')}\nÖnceki cevap: {context.get('last_answer', '')}",
    }


async def get_conversation_context(db, user_id: str, conversation_id: str) -> dict | None:
    return await db.conversation_contexts.find_one(
        {"user_id": user_id, "conversation_id": conversation_id},
        {"_id": 0},
    )


async def save_conversation_context(
    db,
    user_id: str,
    conversation_id: str,
    question: str,
    answer: str,
    package: dict,
    sources: list[dict] | None = None,
):
    document = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "intent": package.get("intent", "general"),
        "target_date": package.get("target_date"),
        "events": (package.get("events") or [])[:5],
        "last_question": question,
        "last_answer": answer,
        "sources": (sources or [])[:5],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.conversation_contexts.replace_one(
        {"user_id": user_id, "conversation_id": conversation_id},
        document,
        upsert=True,
    )