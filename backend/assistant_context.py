"""Build deterministic, real-data conversation context for NOVA."""
import html
import re
from datetime import date, datetime, timedelta
from typing import Optional

import google_integration as gint
from conversation_context import get_conversation_context, resolve_follow_up
from date_resolver import fold_turkish, resolve_requested_date
from intent_router import RouteDecision, route_message
from personal_memory import personal_context_for_keys, personal_memory_reply
from rapidfuzz import fuzz
from response_composer import compose_calendar_answer
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
LIVE_WEB_INTENTS = {
    "travel_search", "hotel_search", "restaurant_search", "cinema_search",
    "event_search", "leisure_search", "shopping_search", "web_search",
}


def _fuzzy_intent(folded: str) -> tuple[Optional[str], int]:
    cleaned = re.sub(r"\bnova\b", "", folded).strip(" ,.!?")
    scores = []
    for intent, examples in INTENT_EXAMPLES.items():
        score = max(fuzz.WRatio(cleaned, example) for example in examples)
        scores.append((intent, round(score)))
    scores.sort(key=lambda item: item[1], reverse=True)
    best_intent, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else 0
    return (best_intent, best_score) if best_score >= 86 and best_score - second_score >= 6 else (None, best_score)


def _has_fuzzy_token(folded: str, options: tuple[str, ...], threshold: int = 78) -> bool:
    tokens = [token for token in re.findall(r"[a-z0-9]+", folded) if len(token) >= 4]
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


def _is_travel_search(folded: str) -> bool:
    transport = (
        "ulasim", "otobus", "ucak", "tren", "yht", "tcdd", "feribot",
        "deniz otobusu", "arabayla", "aracla", "kopru", "rota", "seyahat", "gezi",
    )
    action = ("arastir", "karsilastir", "en mantikli", "fiyat", "bilet", "nasil gider", "rota", "planla", "gidis donus")
    return any(word in folded for word in transport) and any(word in folded for word in action)


def _explicit_live_intent(folded: str) -> Optional[str]:
    if "otel" in folded or "hotels.com" in folded or "konaklama" in folded:
        return "hotel_search"
    if any(term in folded for term in ("sinema", "film seans", "film program")):
        return "cinema_search"
    if any(term in folded for term in ("restoran", "yemek yiy", "corbaci", "kahvalti")) or (
        "corba" in folded and any(term in folded for term in ("bul", "acik", "sonrasi"))
    ):
        return "restaurant_search"
    discovery = any(term in folded for term in ("arastir", "bul", "nereye gidelim", "ne yapalim", "programini arastir"))
    if any(term in folded for term in ("konser", "tiyatro", "etkinlik", "canli muzik", "club")) and discovery:
        return "event_search"
    if ("saatlik" in folded and "plan" in folded) or ("hafta sonu" in folded and "ne yap" in folded):
        return "leisure_search"
    if _is_travel_search(folded) or any(term in folded for term in ("obilet", "flypgs", "pegasus", "turkishairlines", "thy", "ajet")):
        return "travel_search"
    if "iki gunluk" in folded and any(term in folded for term in ("gezi", "plan")):
        return "travel_search"
    return None


def _requires_live_web(folded: str) -> bool:
    markers = (
        "yaknimda", "yakinimda", "su anda acik", "acik corbaci", "guncel fiyat",
        "son haber", "internette arastir", "restoran bul", "otel bul", "etkinlik bul",
        "ucus arastir", "otobus arastir", "tren arastir", "feribot arastir",
        "menu", "musaitlik", "hava durumu", "bugun hava", "bu gece", "guncel saat",
    )
    return any(marker in folded for marker in markers) or bool(_explicit_live_intent(folded))


def _web_needs_workspace(folded: str, target_date: Optional[date]) -> bool:
    own_schedule = ("etkinligim", "programim", "isim var", "konserden sonra", "nikah", "alanya")
    return any(word in folded for word in own_schedule)


def classify_intent(message: str, today: datetime) -> tuple[str, Optional[date]]:
    decision = route_message(message, today)
    return decision.intent, decision.target_date


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
        actionable_terms = ("tiyatral", "nikah", "toplanti", "prova", "cekim", "klip", "randevu")
        if not any(term in folded_event for term in actionable_terms):
            continue

        score = 400 - days * 10 if "tiyatral nikah" in folded_event else 320 - days * 10
        day_label = "Bugün" if days == 0 else ("Yarın" if days == 1 else f"{event_date.day} {TR_MONTHS[event_date.month - 1]}")
        time_text = _time_range(event)
        title = event.get("title", "etkinliğin")
        location = event.get("location", "")
        sentence = f"{day_label} {time_text} {title}"
        if location:
            sentence += f"; yer: {location}"
        candidates.append({"score": score, "label": sentence + "."})

    grouped_tasks = {}
    for task in tasks:
        if fold_turkish(task.get("Durum", "")) in {"tamamlandi", "tamam", "kapali"}:
            continue
        due = _parse_due_date(task.get("Tarih / Son Tarih", ""))
        key = (task.get("Alan", ""), due)
        grouped_tasks.setdefault(key, []).append(task)

    for (area, due), group in grouped_tasks.items():
        days = (due - today.date()).days if due else 999
        score = 240 if days <= 7 else 170 if days <= 14 else 80 if days <= 30 else 20
        text = " ".join(" ".join(str(value) for value in task.values()) for task in group)
        if any(word in fold_turkish(text) for word in ("bilet", "mekan", "ulasim", "otel", "rezervasyon")):
            score += 30

        labels = "; ".join(task.get("İş", "") for task in group)
        if due:
            sentence = f"{due.day} {TR_MONTHS[due.month - 1]}'e kadar {labels}"
        else:
            sentence = labels
        if area:
            sentence += f" ({area})"
        candidates.append({"score": score, "label": sentence + "."})

    for project in _project_focus(projects):
        status = fold_turkish(project.get("Durum", ""))
        project = project.get("Proje", "")
        next_step = project.get("Sonraki Adım", "")
        sentence = f"{project} için sıradaki adım: {next_step}."
        candidates.append({"score": 120 if status == "bekliyor" else 90, "label": sentence})

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)[:3]
    if not ranked:
        return "Bora, şu anda takvim ve İş Merkezi verilerinde acil bir öncelik görünmüyor."

    lines = [f"{index}. {item['label']}" for index, item in enumerate(ranked, 1)]
    return "Bora, şu anda öncelik sıram şöyle:\n" + "\n".join(lines)

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


def _relevant_web_context(message: str, events: list[dict], tasks: list[dict]) -> str:
    stopwords = {"icin", "arastir", "ulasimimi", "sonra", "acik", "bul", "bora", "nova"}
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", fold_turkish(message))
        if len(token) >= 5 and token not in stopwords
    }
    event_lines = [
        _event_line(event)
        for event in events
        if tokens and any(token in fold_turkish(" ".join(str(value) for value in event.values())) for token in tokens)
    ]
    task_lines = [
        " | ".join(str(value) for value in task.values() if value)
        for task in tasks
        if tokens and any(token in fold_turkish(" ".join(str(value) for value in task.values())) for token in tokens)
    ]
    if not event_lines and not task_lines:
        return "Calendar/Workspace içinde sorguyla eşleşen kayıt bulunamadı."
    parts = []
    if event_lines:
        parts.append("İlgili Calendar etkinlikleri:\n" + "\n".join(f"- {line}" for line in event_lines[:5]))
    if task_lines:
        parts.append("İlgili Workspace görevleri:\n" + "\n".join(f"- {line}" for line in task_lines[:8]))
    return "\n\n".join(parts)


async def build_chat_package(
    db,
    user_id: str,
    message: str,
    intent_override: Optional[str] = None,
    conversation_id: str = "default",
    route_decision: Optional[RouteDecision] = None,
) -> dict:
    now = datetime.now(gint.ISTANBUL_TZ)
    stored_context = await get_conversation_context(db, user_id, conversation_id)
    follow_up = resolve_follow_up(message, stored_context)
    decision = route_decision or route_message(message, now)
    intent, target_date = decision.intent, decision.target_date
    memory = None
    if not follow_up and (intent == "personal_memory" or (intent == "general" and decision.memory_context_keys)):
        memory = personal_memory_reply(message, now)
    prior_context = ""
    if follow_up:
        intent = follow_up["intent"]
        prior_context = follow_up.get("prior_context", "")
        if follow_up.get("reply"):
            return {
                "intent": intent,
                "target_date": stored_context.get("target_date") if stored_context else None,
                "calendar_summary": "",
                "workspace_summary": "",
                "core_doc_summary": "",
                "events": (stored_context or {}).get("events", []),
                "pending_count": 0,
                "data_status": {"calendar": None, "sheets": None, "docs_fallback": False},
                "reply": follow_up["reply"],
                "prior_context": "",
                "web_context": "",
            }
    elif memory:
        return {
            "intent": memory["intent"],
            "target_date": None,
            "calendar_summary": "",
            "workspace_summary": "",
            "core_doc_summary": "",
            "events": [],
            "pending_count": 0,
            "data_status": {"calendar": None, "sheets": None, "docs_fallback": False},
            "reply": memory["reply"],
            "prior_context": "",
            "web_context": "",
            "connector": decision.connector,
            "requested_items": decision.requested_items,
        }
    elif decision.memory_context_keys:
        prior_context = personal_context_for_keys(decision.memory_context_keys)
    if intent_override:
        intent = intent_override
        target_date = now.date() if intent in {"briefing", "today_schedule"} else target_date

    workspace_intents = {
        "briefing", "today_schedule", "pending_tasks", "weekly_priorities",
        "weekly_routines", "week_overview", "calendar_date_query",
    }
    folded = fold_turkish(message)
    needs_workspace = intent in workspace_intents or (
        intent in LIVE_WEB_INTENTS and _web_needs_workspace(folded, target_date)
    )
    if not needs_workspace:
        return {
            "intent": intent,
            "target_date": target_date.isoformat() if target_date else None,
            "calendar_summary": "",
            "workspace_summary": "",
            "core_doc_summary": "",
            "events": [],
            "pending_count": 0,
            "data_status": {"calendar": None, "sheets": None, "docs_fallback": False},
            "reply": None,
            "prior_context": prior_context,
            "web_context": "",
            "connector": decision.connector,
            "requested_items": decision.requested_items,
        }

    if intent in {"weekly_priorities", "weekly_routines", "week_overview"}:
        query_start = now.date() - timedelta(days=now.weekday())
        query_end = query_start + timedelta(days=7)
    else:
        query_start = decision.range_start or target_date or now.date()
        query_end = decision.range_end or (query_start + timedelta(days=1))
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
        reply = compose_calendar_answer(target_date or query_start, events, calendar_ok, message)
    elif intent == "today_schedule":
        reply = service_today_schedule(events, projects, calendar_ok)
    elif intent == "briefing":
        briefing_now = now
        if target_date and target_date != now.date():
            briefing_now = datetime.combine(target_date, now.timetz())
        reply = service_briefing(events, tasks, projects, routines, briefing_now, calendar_ok, sheet_ok)
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

    web_context = (
        _relevant_web_context(message, events, tasks)
        if intent in LIVE_WEB_INTENTS
        else "\n\n".join(part for part in (calendar_summary, _workspace_summary(sheet)) if part)
    )
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
        "prior_context": prior_context,
        "web_context": web_context,
        "connector": decision.connector,
        "requested_items": decision.requested_items,
    }
