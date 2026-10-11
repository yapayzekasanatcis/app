"""Explicit read connector execution for central RouteDecision."""
from datetime import timedelta

import google_integration as gint
from capability_registry import capability_message
from date_resolver import fold_turkish
from response_composer import compose_availability, meta_reply
from workspace_data import rows_to_dicts


def _rows_summary(tab: str, rows: list, message: str = "") -> str:
    records = rows_to_dicts(rows)
    if not records:
        return f"Bora, NOVA İş Merkezi’ndeki {tab} sayfasında kayıt göremiyorum."

    folded = fold_turkish(message)
    if tab == "İşler" and any(term in folded for term in (
        "gorevi hakkinda", "gorev hakkinda", "kayitli bilgileri",
        "durumunu", "durumu", "kontrol et"
    )):
        stop = {
            "gorevi", "gorev", "hakkinda", "bana", "sadece", "workspace",
            "kayitli", "bilgileri", "soyle", "internette", "arastirma", "yapma",
            "durumunu", "durumu", "kontrol", "workspace", "workspace'ten"
        }
        tokens = [
            token for token in folded.replace("'", " ").split()
            if len(token) >= 4 and token not in stop
        ]
        matches = []
        for record in records:
            haystack = fold_turkish(" ".join(str(value) for value in record.values()))
            score = sum(1 for token in tokens if token in haystack)
            if score:
                matches.append((score, record))
        if matches:
            matches.sort(key=lambda item: item[0], reverse=True)
            record = matches[0][1]

            task_name = record.get("İş", "Görev")
            status = record.get("Durum", "")
            due = record.get("Tarih / Son Tarih", "")
            note = record.get("Not", "")

            reply = f"Bora, {task_name} görevi {status or 'durumu belirtilmemiş'} görünüyor."
            if due:
                reply += f" Son tarih {due}."
            if note:
                reply += f" Notta şu bilgi var: {note}"
            return reply

    lines = []
    for record in records[:8]:
        values = [str(value) for value in record.values() if value]
        lines.append("- " + " | ".join(values))
    return f"Bora, NOVA İş Merkezi · {tab} sayfasındaki kayıtlar:\n" + "\n".join(lines)


async def execute_read_connector(decision, message: str, db, user_id: str, registry: dict) -> dict | None:
    if decision.intent == "meta":
        return {"reply": meta_reply(message), "source": "Conversation", "events": []}
    if decision.intent == "gmail_read":
        error = capability_message(registry, "gmail.read", "Gmail")
        return {"reply": error or "Bora, Gmail bağlantısı şu anda aktif değil.", "source": "Capability Registry", "events": []}
    if decision.intent == "drive_read":
        error = capability_message(registry, "drive.read", "Drive")
        if error:
            return {"reply": error, "source": "Capability Registry", "events": []}
        data = await gint.get_drive_folder_files(db, user_id)
        files = data.get("files", []) if data else []
        answer = "Bora, Drive’daki NOVA ASİSTAN klasöründe " + (", ".join(item.get("name", "") for item in files[:20]) if files else "dosya görünmüyor") + "."
        return {"reply": answer, "source": "Google Drive", "events": []}
    if decision.intent == "docs_read":
        error = capability_message(registry, "docs.read", "Google Docs")
        if error:
            return {"reply": error, "source": "Capability Registry", "events": []}
        title = decision.target_document or gint.DOC_NAME
        doc = await gint.get_doc_text_by_name(db, user_id, title)
        if not doc:
            return {"reply": f"Bora, Docs’ta '{title}' adlı belgeyi bulamadım.", "source": "Google Docs", "events": []}
        folded = fold_turkish(message)
        lines = [line.strip() for line in doc["text"].splitlines() if line.strip()]
        if "komagene" in folded:
            selected = [line for line in lines if "komagene" in fold_turkish(line)][:8]
        else:
            selected = lines[:8]
        return {"reply": f"Bora, {title} belgesinden özet:\n" + "\n".join(f"- {line}" for line in selected), "source": "Google Docs", "events": []}
    if decision.intent == "sheets_read":
        error = capability_message(registry, "sheets.read", "Google Sheets")
        if error:
            return {"reply": error, "source": "Capability Registry", "events": []}
        tab = decision.target_tab
        if not tab:
            return {"reply": "Bora, NOVA İş Merkezi’nde İşler, Projeler veya Rutinler sayfasından hangisini istediğini belirtir misin?", "source": "Google Sheets", "events": []}
        data = await gint.get_sheet_tab_data(db, user_id, tab)
        if not data:
            return {"reply": f"Bora, NOVA İş Merkezi’nde {tab} sayfasını bulamadım.", "source": "Google Sheets", "events": []}
        return {"reply": _rows_summary(tab, data["rows"], message), "source": f"Google Sheets · {tab}", "events": []}
    if decision.intent == "personal_work":
        start = decision.range_start or decision.target_date
        if start is None:
            from datetime import datetime
            start = datetime.now(gint.ISTANBUL_TZ).date()
        events = await gint.get_calendar_events_for_range(db, user_id, start, start + timedelta(days=121))
        sheet = await gint.get_sheet_data(db, user_id) or {}
        tasks = rows_to_dicts(sheet.get("İşler", []))
        selected_events = [event for event in events if any(term in fold_turkish(event.get("title", "")) for term in ("tiyatral", "nikah"))]
        selected_tasks = [task for task in tasks if any(term in fold_turkish(" ".join(str(value) for value in task.values())) for term in ("tiyatral", "nikah"))]
        lines = [f"- {event.get('start','')[:10]} {event.get('title')}" for event in selected_events[:8]]
        lines += [f"- {task.get('İş')} ({task.get('Durum')})" for task in selected_tasks[:8]]
        return {"reply": "Bora, Tiyatral Nikâh iş listen:\n" + ("\n".join(lines) if lines else "Kayıt görünmüyor."), "source": "Calendar + Google Sheets · İşler", "events": selected_events}
    if decision.intent == "availability":
        target = decision.target_date
        if not target:
            from datetime import datetime
            target = datetime.now(gint.ISTANBUL_TZ).date()
        error = capability_message(registry, "calendar.read", "Calendar")
        if error:
            return {"reply": error, "source": "Capability Registry", "events": []}
        events = await gint.get_calendar_events_for_date(db, user_id, target)
        return {"reply": compose_availability(target, decision.target_time, events, True), "source": "Google Calendar · Availability", "events": events}
    return None