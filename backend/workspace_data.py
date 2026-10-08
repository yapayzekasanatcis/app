"""Shared normalized Google Workspace data for chat and every application page."""
import re
from datetime import date, datetime, timedelta
from typing import Optional

import google_integration as gint
from date_resolver import fold_turkish


def rows_to_dicts(rows: list) -> list[dict]:
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [
        {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        for row in rows[1:]
    ]


def _parse_due_date(value: str) -> Optional[date]:
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", value or "")
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _context_for(value: str) -> str:
    folded = fold_turkish(value)
    if "komagene" in folded:
        return "komagene"
    if "tiyatral" in folded or "nikah" in folded:
        return "tiyatral-nikah"
    if "bora ai" in folded or "study" in folded or "proje" in folded:
        return "bora-ai-studyo"
    return "kisisel"


def _priority_value(value: str) -> str:
    folded = fold_turkish(value)
    if "yuksek" in folded:
        return "yuksek"
    if "dusuk" in folded:
        return "dusuk"
    return "normal"


def normalize_tasks(rows: list[dict], today: date) -> list[dict]:
    items = []
    for index, row in enumerate(rows):
        status = row.get("Durum", "")
        if fold_turkish(status) in {"tamam", "tamamlandi", "kapali"}:
            continue
        due = _parse_due_date(row.get("Tarih / Son Tarih", ""))
        days_left = (due - today).days if due else None
        priority = _priority_value(row.get("Öncelik", ""))
        score = {"yuksek": 100, "normal": 60, "dusuk": 20}[priority]
        if days_left is not None:
            score += 80 if days_left <= 7 else 50 if days_left <= 14 else 20 if days_left <= 30 else 0
        text = " ".join(str(value) for value in row.values())
        if any(word in fold_turkish(text) for word in ("bilet", "mekan", "otel", "ulasim", "rezervasyon")):
            score += 20
        items.append({
            "id": f"sheet-task-{index}",
            "title": row.get("İş", "(başlıksız iş)"),
            "description": row.get("Not", ""),
            "area": row.get("Alan", ""),
            "status": status,
            "due_label": row.get("Tarih / Son Tarih", ""),
            "due_date": due.isoformat() if due else None,
            "days_left": days_left,
            "priority": priority,
            "priority_label": row.get("Öncelik", "Normal") or "Normal",
            "priority_score": score,
            "context": _context_for(row.get("Alan", "")),
            "source": "Google Sheets · İşler",
        })
    return sorted(items, key=lambda item: (-item["priority_score"], item["due_date"] or "9999-12-31"))


def normalize_projects(rows: list[dict]) -> list[dict]:
    items = []
    for index, row in enumerate(rows):
        status = row.get("Durum", "")
        items.append({
            "id": f"sheet-project-{index}",
            "title": row.get("Proje", "(başlıksız proje)"),
            "description": row.get("Not", ""),
            "area": row.get("Alan", "Bora AI Stüdyo"),
            "status": status,
            "period": row.get("Dönem", ""),
            "next_step": row.get("Sonraki Adım", ""),
            "due_label": row.get("Dönem", ""),
            "priority": "yuksek" if fold_turkish(status) == "bekliyor" else "normal",
            "priority_label": status or "Aktif",
            "priority_score": 85 if fold_turkish(status) == "bekliyor" else 55,
            "context": "bora-ai-studyo" if "bora ai" in fold_turkish(row.get("Alan", "Bora AI")) else _context_for(row.get("Alan", "")),
            "source": "Google Sheets · Projeler",
        })
    return items


def normalize_routines(rows: list[dict]) -> list[dict]:
    items = []
    for index, row in enumerate(rows):
        if fold_turkish(row.get("Durum", "")) != "aktif":
            continue
        items.append({
            "id": f"sheet-routine-{index}",
            "title": row.get("Rutin", "(başlıksız rutin)"),
            "area": row.get("Alan", ""),
            "schedule": row.get("Tekrar", ""),
            "time": row.get("Saat / Son Saat", ""),
            "rule": row.get("Kural / Not", ""),
            "status": row.get("Durum", ""),
            "context": _context_for(row.get("Alan", "")),
            "source": "Google Sheets · Rutinler",
        })
    return items


def normalize_events(events: list[dict]) -> list[dict]:
    normalized = []
    for event in events:
        context_text = " ".join(str(event.get(key, "")) for key in ("title", "description"))
        normalized.append({
            "id": event.get("id"),
            "title": event.get("title", "(başlıksız etkinlik)"),
            "description": event.get("description", ""),
            "start_time": event.get("start"),
            "end_time": event.get("end"),
            "location": event.get("location", ""),
            "context": _context_for(context_text),
            "calendar": event.get("calendar"),
            "link": event.get("link"),
            "source": "Google Calendar",
        })
    return normalized


async def load_workspace_source(db, user_id: str, start_date: date, end_date: date) -> dict:
    sheet, events = None, []
    sheet_ok, calendar_ok = True, True
    try:
        sheet = await gint.get_sheet_data(db, user_id)
    except Exception:
        sheet_ok = False
    try:
        events = await gint.get_calendar_events_for_range(db, user_id, start_date, end_date)
    except Exception:
        calendar_ok = False
    return {
        "sheet": sheet,
        "events": events,
        "sheet_ok": sheet_ok,
        "calendar_ok": calendar_ok,
    }


async def build_workspace_snapshot(db, user_id: str) -> dict:
    now = datetime.now(gint.ISTANBUL_TZ)
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    source = await load_workspace_source(db, user_id, week_start, today + timedelta(days=121))
    sheet = source["sheet"] or {}
    tasks = normalize_tasks(rows_to_dicts(sheet.get("İşler", [])), today)
    projects = normalize_projects(rows_to_dicts(sheet.get("Projeler", [])))
    routines = normalize_routines(rows_to_dicts(sheet.get("Rutinler", [])))
    events = normalize_events(source["events"])

    day_key = today.isoformat()
    tomorrow_key = (today + timedelta(days=1)).isoformat()
    active_projects = [p for p in projects if fold_turkish(p["status"]) in {"aktif", "bekliyor"}]
    priorities = sorted([*tasks, *active_projects], key=lambda item: -item.get("priority_score", 0))[:6]
    tiyatral_events = [e for e in events if e["context"] == "tiyatral-nikah"]
    personal = [item for item in [*events, *tasks, *projects, *routines] if item["context"] == "kisisel"]

    return {
        "generated_at": now.isoformat(),
        "timezone": "Europe/Istanbul",
        "anchor_date": day_key,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "sources": {
            "calendar": {"connected": source["calendar_ok"], "name": gint.CALENDAR_NAME},
            "sheets": {"connected": source["sheet_ok"] and bool(sheet), "name": gint.SHEET_NAME},
        },
        "today_events": [e for e in events if (e.get("start_time") or "")[:10] == day_key],
        "tomorrow_events": [e for e in events if (e.get("start_time") or "")[:10] == tomorrow_key],
        "week_events": [e for e in events if week_start.isoformat() <= (e.get("start_time") or "")[:10] < week_end.isoformat()],
        "calendar_events": events,
        "pending_tasks": tasks,
        "priorities": priorities,
        "komagene": {"routines": [r for r in routines if r["context"] == "komagene"]},
        "tiyatral": {
            "events": tiyatral_events,
            "tasks": [task for task in tasks if task["context"] == "tiyatral-nikah"],
        },
        "bora_ai": {"projects": active_projects},
        "personal": {"items": personal},
    }
