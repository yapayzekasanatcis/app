"""Build deterministic, real-data conversation context for NOVA."""
import html
import re
from datetime import date, datetime, timedelta
from typing import Optional

import google_integration as gint
from date_resolver import fold_turkish, resolve_requested_date


TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
TR_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def rows_to_dicts(rows: list) -> list[dict]:
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [
        {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        for row in rows[1:]
    ]


def classify_intent(message: str, today: datetime) -> tuple[str, Optional[date]]:
    folded = fold_turkish(message)
    is_week = "bu hafta" in folded or "haftanin" in folded
    if is_week and ("rutin" in folded or "komagene" in folded):
        return "weekly_routines", None
    if is_week and any(word in folded for word in ("onemli", "oncelik", "islerim", "ne yap")):
        return "weekly_priorities", None
    if is_week:
        return "week_overview", None
    target = resolve_requested_date(message, today)
    if target:
        return ("today" if target == today.date() else "date"), target
    if "program" in folded and "bugun" in folded:
        return "today", today.date()
    return "general", today.date()


def _clean_description(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(without_tags).split())


def _date_label(value: date) -> str:
    return f"{value.day} {TR_MONTHS[value.month - 1]} {TR_WEEKDAYS[value.weekday()]}"


def _time_range(event: dict) -> str:
    start = event.get("start", "")
    end = event.get("end", "")
    if "T" not in start:
        return "tüm gün"
    return f"{start[11:16]}–{end[11:16]}" if "T" in end else start[11:16]


def _event_line(event: dict, include_description: bool = True) -> str:
    details = [f"{_time_range(event)} {event.get('title', '(başlıksız)')}"]
    if event.get("location"):
        details.append(event["location"])
    description = _clean_description(event.get("description", "")) if include_description else ""
    if description:
        details.append(description)
    return " — ".join(details)


def _project_focus(projects: list[dict]) -> list[dict]:
    eligible = [p for p in projects if fold_turkish(p.get("Durum", "")) in {"aktif", "bekliyor"}]

    def score(project: dict) -> int:
        status = fold_turkish(project.get("Durum", ""))
        text = fold_turkish(" ".join(str(value) for value in project.values()))
        return (100 if status == "bekliyor" else 40) + (60 if "kadina siddet" in text else 0)

    return sorted(eligible, key=score, reverse=True)[:2]


def _project_sentence(projects: list[dict]) -> str:
    focus = _project_focus(projects)
    if not focus:
        return ""
    rendered = [f"{p.get('Proje')} ({p.get('Durum')}; sonraki adım: {p.get('Sonraki Adım')})" for p in focus]
    return "Bora AI Stüdyo tarafında " + "; ".join(rendered) + "."


def _parse_due_date(value: str) -> Optional[date]:
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", value or "")
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _priority_reply(today: datetime, events: list, tasks: list[dict], projects: list[dict]) -> str:
    candidates = []
    for event in events:
        start = event.get("start", "")
        event_date = date.fromisoformat(start[:10]) if len(start) >= 10 else today.date()
        if event_date < today.date():
            continue
        days = (event_date - today.date()).days
        folded_event = fold_turkish(" ".join(str(event.get(key, "")) for key in ("title", "description")))
        if "tiyatral nikah" in folded_event:
            event_score = 400 - days * 10
        elif "komagene" in folded_event:
            event_score = 140 - days * 5
        else:
            event_score = 320 - days * 10
        candidates.append({
            "score": event_score,
            "label": f"{_date_label(event_date)} {_event_line(event, include_description=False)}",
        })

    grouped_tasks = {}
    for task in tasks:
        if fold_turkish(task.get("Durum", "")) in {"tamamlandi", "tamam"}:
            continue
        due = _parse_due_date(task.get("Tarih / Son Tarih", ""))
        key = (task.get("Alan", ""), due)
        grouped_tasks.setdefault(key, []).append(task)
    for (area, due), group in grouped_tasks.items():
        days = (due - today.date()).days if due else 999
        if days <= 7:
            score = 240
        elif days <= 14:
            score = 170
        elif days <= 30:
            score = 80
        else:
            score = 20
        text = " ".join(" ".join(str(value) for value in task.values()) for task in group)
        folded = fold_turkish(text)
        if any(word in folded for word in ("bilet", "mekan", "ulasim", "otel", "rezervasyon")):
            score += 30
        labels = "; ".join(task.get("İş", "") for task in group)
        due_label = f"son tarih {due.day} {TR_MONTHS[due.month - 1]}" if due else "tarih belirtilmemiş"
        candidates.append({"score": score, "label": f"{area}: {labels} ({due_label})"})

    for project in _project_focus(projects):
        status = fold_turkish(project.get("Durum", ""))
        candidates.append({
            "score": 120 if status == "bekliyor" else 90,
            "label": f"{project.get('Proje')}: {project.get('Sonraki Adım')} ({project.get('Durum')})",
        })

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)[:3]
    if not ranked:
        return "Bora, bu hafta için gerçek takvim veya İş Merkezi verisinde öncelik görünmüyor."
    lines = [f"{index}. {item['label']}" for index, item in enumerate(ranked, 1)]
    project_note = _project_sentence(projects)
    return "Bora, bu haftanın en önemli üç işi şöyle:\n" + "\n".join(lines) + (f"\n\n{project_note}" if project_note else "")


def _weekly_routines_reply(today: datetime, routines: list[dict]) -> str:
    weekday_map = {fold_turkish(name): index for index, name in enumerate(TR_WEEKDAYS)}
    past, current, remaining = [], [], []
    for routine in routines:
        if fold_turkish(routine.get("Alan", "")) != "komagene":
            continue
        if fold_turkish(routine.get("Durum", "")) != "aktif":
            continue
        repeat = fold_turkish(routine.get("Tekrar", ""))
        matched = next((name for name in weekday_map if re.search(rf"\b{name}\b", repeat)), None)
        if not matched:
            continue
        item = routine.get("Rutin", "")
        time_value = routine.get("Saat / Son Saat", "")
        rendered = f"{TR_WEEKDAYS[weekday_map[matched]]}: {item}" + (f" ({time_value})" if time_value else "")
        day_index = weekday_map[matched]
        if day_index < today.weekday():
            past.append(rendered)
        elif day_index == today.weekday():
            current.append(rendered)
        else:
            remaining.append(rendered)
    parts = ["Bora, Komagene rutinlerini haftanın akışına göre ayırdım."]
    parts.append("Haftanın geçmiş kısmı: " + ("; ".join(past) if past else "rutin yok" ) + ".")
    if current:
        parts.append("Bugün: " + "; ".join(current) + ".")
    parts.append("Kalan işler: " + ("; ".join(remaining) if remaining else "rutin yok") + ".")
    return " ".join(parts)


def _workspace_summary(sheet: Optional[dict]) -> str:
    if not sheet:
        return "NOVA İş Merkezi bulunamadı."
    sections = []
    for tab in ("İşler", "Projeler", "Rutinler"):
        rows = sheet.get(tab, [])
        sections.append(f"{tab}:\n" + ("\n".join(" | ".join(map(str, row)) for row in rows[:30]) or "VERİ YOK"))
    return "\n\n".join(sections)


async def build_chat_package(db, user_id: str, message: str) -> dict:
    now = datetime.now(gint.ISTANBUL_TZ)
    intent, target_date = classify_intent(message, now)
    sheet = await gint.get_sheet_data(db, user_id)
    tasks = rows_to_dicts(sheet.get("İşler", [])) if sheet else []
    projects = rows_to_dicts(sheet.get("Projeler", [])) if sheet else []
    routines = rows_to_dicts(sheet.get("Rutinler", [])) if sheet else []

    if intent in {"weekly_priorities", "weekly_routines", "week_overview"}:
        week_start = now.date() - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        events = await gint.get_calendar_events_for_range(db, user_id, week_start, week_end)
    else:
        query_date = target_date or now.date()
        events = await gint.get_calendar_events_for_date(db, user_id, query_date)

    calendar_summary = "\n".join(f"- {_event_line(event)}" for event in events) or "Etkinlik YOK"
    reply = None
    if intent == "date":
        label = _date_label(target_date)
        if events:
            reply = f"Bora, {label} programında " + " ".join(_event_line(event).rstrip(".") + "." for event in events)
        else:
            reply = f"Bora, {label} için NOVA özel takviminde etkinlik görünmüyor."
    elif intent == "today":
        program = " ".join(_event_line(event, include_description=False).rstrip(".") + "." for event in events) if events else "takviminde etkinlik görünmüyor."
        project_note = _project_sentence(projects)
        reply = f"Bora, bugün {program}" + (f" {project_note}" if project_note else "")
    elif intent == "weekly_priorities":
        reply = _priority_reply(now, events, tasks, projects)
    elif intent == "weekly_routines":
        reply = _weekly_routines_reply(now, routines)
    elif intent == "week_overview":
        past_events = [event for event in events if event.get("start", "")[:10] < now.date().isoformat()]
        upcoming_events = [event for event in events if event.get("start", "")[:10] >= now.date().isoformat()]
        past_text = "; ".join(_event_line(event, include_description=False) for event in past_events) or "etkinlik yok"
        upcoming_text = "; ".join(_event_line(event, include_description=False) for event in upcoming_events) or "etkinlik yok"
        project_note = _project_sentence(projects)
        reply = f"Bora, haftanın geçmiş kısmı: {past_text}. Kalan program: {upcoming_text}." + (f" {project_note}" if project_note else "")

    return {
        "intent": intent,
        "target_date": target_date.isoformat() if target_date else None,
        "calendar_summary": calendar_summary,
        "workspace_summary": _workspace_summary(sheet),
        "reply": reply,
    }
