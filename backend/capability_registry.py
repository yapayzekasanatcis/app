"""Truthful runtime capability state derived from granted scopes and probes."""
import os
import time

import google_integration as gint


_CACHE: dict[str, dict] = {}
_TTL_SECONDS = 300

CALENDAR_READ = {
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
}
CALENDAR_WRITE = {"https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/calendar.events"}
SHEETS_READ = {
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
}
SHEETS_WRITE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_READ = "https://www.googleapis.com/auth/drive.readonly"
DOCS_READ = "https://www.googleapis.com/auth/documents.readonly"
GMAIL_READ = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.metadata",
}


def _entry(granted: bool, runtime: str = "not_granted", error: str | None = None) -> dict:
    return {"granted": granted, "available": granted and runtime == "verified", "runtime": runtime, "error": error}


async def get_capability_registry(db, user_id: str, force: bool = False) -> dict:
    cached = _CACHE.get(user_id)
    if cached and not force and time.monotonic() - cached["stored_at"] < _TTL_SECONDS:
        return cached["value"]
    token = await db.google_tokens.find_one({"user_id": user_id}, {"_id": 0, "scopes": 1}) or {}
    scopes = set(token.get("scopes") or [])
    connected = bool(token)
    registry = {
        "calendar.read": _entry(connected and bool(scopes & CALENDAR_READ), "granted" if scopes & CALENDAR_READ else "not_granted"),
        "calendar.write": _entry(bool(scopes & CALENDAR_WRITE), "granted" if scopes & CALENDAR_WRITE else "not_granted"),
        "sheets.read": _entry(connected and bool(scopes & SHEETS_READ), "granted" if scopes & SHEETS_READ else "not_granted"),
        "sheets.write": _entry(SHEETS_WRITE in scopes, "granted" if SHEETS_WRITE in scopes else "not_granted"),
        "drive.read": _entry(connected and DRIVE_READ in scopes, "granted" if DRIVE_READ in scopes else "not_granted"),
        "docs.read": _entry(connected and DOCS_READ in scopes, "granted" if DOCS_READ in scopes else "not_granted"),
        "gmail.read": _entry(bool(scopes & GMAIL_READ), "granted" if scopes & GMAIL_READ else "not_granted"),
        "gemini_search": _entry(bool(os.environ.get("EMERGENT_LLM_KEY")), "verified" if os.environ.get("EMERGENT_LLM_KEY") else "not_granted"),
    }
    if connected:
        try:
            creds = await gint.credentials_for(db, user_id)
            calendar = gint._service("calendar", "v3", creds)
            gint._http(calendar.calendarList().list(maxResults=1, fields="items(id)"))
            registry["calendar.read"].update(available=True, runtime="verified", error=None)
        except Exception as exc:
            registry["calendar.read"].update(available=False, runtime="error", error=type(exc).__name__)
        try:
            drive = gint._service("drive", "v3", creds)
            gint._http(drive.files().list(pageSize=1, fields="files(id)"))
            registry["drive.read"].update(available=True, runtime="verified", error=None)
        except Exception as exc:
            registry["drive.read"].update(available=False, runtime="error", error=type(exc).__name__)
        for key, probe in (("sheets.read", gint.get_sheet_data), ("docs.read", gint.get_core_doc_text)):
            if registry[key]["granted"]:
                try:
                    await probe(db, user_id)
                    registry[key].update(available=True, runtime="verified", error=None)
                except Exception as exc:
                    registry[key].update(available=False, runtime="error", error=type(exc).__name__)
    _CACHE[user_id] = {"stored_at": time.monotonic(), "value": registry}
    return registry


def capability_message(registry: dict, capability: str, label: str) -> str:
    state = registry.get(capability, {})
    if state.get("available"):
        return ""
    if not state.get("granted"):
        return f"Bora, {label} bağlantısı/yetkisi şu anda aktif değil."
    return f"Bora, şu anda {label} bağlantısından sonuç alamıyorum."