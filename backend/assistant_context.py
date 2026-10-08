"""Build deterministic, real-data conversation context for NOVA."""
import html
import re
from datetime import date, datetime, timedelta
from typing import Optional

import google_integration as gint
from date_resolver import fold_turkish, resolve_requested_date
from rapidfuzz import fuzz
from workspace_data import load_workspace_source, rows_to_dicts


TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
TR_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
INTENT_EXAMPLES = {
    "briefing": [
        "gunun brifingini sesli oku", "briefingimi oku", "brifingimi oku",
        "gunun ozetini oku", "sabah brifingimi anlat", "bugunun ozetini soyle",
    ],
    "today_schedule": [
        "bugun programim ne", "bugunku programim ne", "bugun ne var",
        "gunun programini soyle", "bugunku takvimimi anlat", "bugun ne yapiyorum",
    ],
    "pending_tasks": [
        "bekleyen islerimi oku", "bekleyen gorevlerim ne", "yapilacak islerimi soyle",
        "tamamlanmamis islerim ne", "bekleyen isleri anlat", "acik gorevlerimi oku",
    ],
    "weekly_priorities": [
        "bu hafta en onemli islerim ne", "haftalik onceliklerimi soyle",
        "bu haftanin onceliklerini oku", "bu hafta neye odaklanmaliyim",
    ],
}


def _fuzzy_intent(folded: str) -> tuple[Optional[str], int]:
    cleaned = re.sub(r"\bnova\b", "", folded).strip(" ,.!?")
    best_intent, best_score = None, 0
    for intent, examples in INTENT_EXAMPLES.items():
        score = max(fuzz.WRatio(cleaned, example) for example in examples)
        if score > best_score:
            best_intent, best_score = intent, round(score)
    return (best_intent, best_score) if best_score >= 70 else (None, best_score)


def _has_fuzzy_token(folded: str, options: tuple[str, ...], threshold: int = 78) -> bool:
    tokens = re.findall(r"[a-z0-9]+", folded)
    return any(
        fuzz.partial_ratio(token, option) >= threshold
        for token in tokens
        for option in options
    )


def _semantic_intent(folded: str) -> Optional[str]:
    if _has_fuzzy_token(folded, ("bekleyen", "tamamlanmamis", "yapilacak")) and _has_fuzzy_token(
        folded, ("is", "gorev"), threshold=72
    ):
        return "pending_tasks"
    if _has_fuzzy_token(folded, ("brifing", "briefing", "ozet")):
        return "briefing"
    if _has_fuzzy_token(folded, ("bugun", "bugunku", "gunun")) and (
        _has_fuzzy_token(folded, ("program", "takvim")) or "ne var" in folded
    ):
        return "today_schedule"
    return None


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
    if target and target != today.date():
        return "calendar_date_query", target
    semantic_intent = _semantic_intent(folded)
    if semantic_intent:
        return semantic_intent, today.date() if semantic_intent in {"briefing", "today_schedule"} else None
    fuzzy_intent, _score = _fuzzy_intent(folded)
    if fuzzy_intent:
        return fuzzy_intent, today.date() if fuzzy_intent in {"briefing", "today_schedule"} else None
    if target:
        return "today_schedule", target
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


def service_calendar_date_query(target_date: date, events: list, calendar_ok: bool) -> str:
    label = _date_label(target_date)
    if not calendar_ok:
        return f"Bora, {label} için Google Takvim şu anda okunamadı; program yok diyemem."
    if not events:
        return f"Bora, {label} için NOVA özel takviminde etkinlik görünmüyor."
    return f"Bora, {label} programında " + " ".join(
        _event_line(event).rstrip(".") + "." for event in events
    )


def service_today_schedule(events: list, projects: list[dict], calendar_ok: bool) -> str:
    if calendar_ok:
        program = (
            " ".join(_event_line(event, include_description=False).rstrip(".") + "." for event in events)
            if events else "takviminde etkinlik görünmüyor."
        )
    else:
        program = "Google Takvim şu anda okunamadı; program yok diyemem."
    project_note = _project_sentence(projects)
    return f"Bora, bugün {program}" + (f" {project_note}" if project_note else "")


def service_pending_tasks(tasks: list[dict], sheet_ok: bool) -> str:
    if not sheet_ok:
        return "Bora, NOVA İş Merkezi şu anda okunamadı; bekleyen işin yok diyemem."
    pending = [
        task for task in tasks
        if fold_turkish(task.get("Durum", "")) not in {"tamam", "tamamlandi", "kapali"}
    ]
    if not pending:
        return "Bora, NOVA İş Merkezi'nde bekleyen iş görünmüyor."
    lines = []
    for task in pending:
        due = task.get("Tarih / Son Tarih", "")
        priority = task.get("Öncelik", "")
        suffix = ", ".join(value for value in (due, priority) if value)
        lines.append(f"- {task.get('İş')}" + (f" ({suffix})" if suffix else ""))
    return f"Bora, NOVA İş Merkezi'nde {len(pending)} bekleyen iş var:\n" + "\n".join(lines)


def service_briefing(
    events: list,
    tasks: list[dict],
    projects: list[dict],
    routines: list[dict],
    now: datetime,
    calendar_ok: bool,
    sheet_ok: bool,
) -> str:
    schedule = service_today_schedule(events, projects, calendar_ok).removeprefix("Bora, ")
    pending = [task for task in tasks if fold_turkish(task.get("Durum", "")) not in {"tamam", "tamamlandi", "kapali"}]
    today_name = fold_turkish(TR_WEEKDAYS[now.weekday()])
    today_routines = []
    for routine in routines:
        if fold_turkish(routine.get("Durum", "")) != "aktif":
            continue
        if re.search(rf"\b{today_name}\b", fold_turkish(routine.get("Tekrar", ""))):
            today_routines.append(routine.get("Rutin", ""))
    task_text = (
        f"İş Merkezi'nde {len(pending)} bekleyen iş var; ilk sırada {pending[0].get('İş')}."
        if sheet_ok and pending else
        ("İş Merkezi'nde bekleyen iş görünmüyor." if sheet_ok else "İş Merkezi şu anda okunamadı.")
    )
    routine_text = f"Bugünün aktif rutini: {'; '.join(today_routines)}." if today_routines else ""
    date_label = _date_label(now.date())
    return " ".join(part for part in (f"Bora, {date_label} gününün özeti: {schedule}", task_text, routine_text) if part)


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


def service_weekly_priorities(today: datetime, events: list, tasks: list[dict], projects: list[dict]) -> str:
    return _priority_reply(today, events, tasks, projects)


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


async def build_chat_package(db, user_id: str, message: str, intent_override: Optional[str] = None) -> dict:
    now = datetime.now(gint.ISTANBUL_TZ)
    intent, target_date = classify_intent(message, now)
    if intent_override:
        intent = intent_override
        target_date = now.date() if intent in {"briefing", "today_schedule"} else target_date
    if intent in {"weekly_priorities", "weekly_routines", "week_overview"}:
        query_start = now.date() - timedelta(days=now.weekday())
        query_end = query_start + timedelta(days=7)
    else:
        query_start = target_date or now.date()
        query_end = query_start + timedelta(days=1)
    source = await load_workspace_source(db, user_id, query_start, query_end)
    sheet = source["sheet"]
    sheet_ok = source["sheet_ok"]
    tasks = rows_to_dicts(sheet.get("İşler", [])) if sheet else []
    projects = rows_to_dicts(sheet.get("Projeler", [])) if sheet else []
    routines = rows_to_dicts(sheet.get("Rutinler", [])) if sheet else []

    events = source["events"]
    calendar_ok = source["calendar_ok"]

    core_doc = None
    if not calendar_ok and not sheet_ok:
        try:
            core_doc = await gint.get_core_doc_text(db, user_id)
        except Exception:
            core_doc = None

    calendar_summary = "\n".join(f"- {_event_line(event)}" for event in events) or "Etkinlik YOK"
    reply = None
    if intent == "calendar_date_query":
        reply = service_calendar_date_query(target_date, events, calendar_ok)
    elif intent == "today_schedule":
        reply = service_today_schedule(events, projects, calendar_ok)
    elif intent == "briefing":
        reply = service_briefing(events, tasks, projects, routines, now, calendar_ok, sheet_ok)
    elif intent == "pending_tasks":
        reply = service_pending_tasks(tasks, sheet_ok)
    elif intent == "weekly_priorities":
        reply = service_weekly_priorities(now, events, tasks, projects)
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
        "core_doc_summary": core_doc["text"][:2000] if core_doc else "",
        "events": events,
        "pending_count": len([task for task in tasks if fold_turkish(task.get("Durum", "")) not in {"tamam", "tamamlandi", "kapali"}]),
        "data_status": {"calendar": calendar_ok, "sheets": sheet_ok, "docs_fallback": bool(core_doc)},
        "reply": reply,
    }
