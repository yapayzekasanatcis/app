"""Google OAuth 2.0 + Calendar/Sheets/Drive/Docs read integration."""
import logging
import os
from datetime import date, datetime, timezone, timedelta
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("nova.google")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")
TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")

fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode()) if TOKEN_ENCRYPTION_KEY else None

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

CALENDAR_NAME = "NOVA ASİSTAN — Özel Takvim"
SHEET_NAME = "NOVA İş Merkezi"
DRIVE_FOLDER_NAME = "NOVA ASİSTAN"
DOC_NAME = "NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler"
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
EXPECTED_CALENDAR_EVENT_TITLE = "Sezon Açılış Konseri — Bursa Bölge Devlet Senfoni Orkestrası"
EXPECTED_CALENDAR_EVENT_LOCATION = "Merinos AKKM Osmangazi Salonu"


class OAuthAccessLogFilter(logging.Filter):
    """Keep authorization codes and OAuth state out of access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) < 3:
            return True
        path = record.args[2]
        if not isinstance(path, str) or "/api/google/callback?" not in path:
            return True
        parts = urlsplit(path)
        redacted = []
        sensitive = {"code", "state", "access_token", "refresh_token", "client_secret"}
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            redacted.append((key, "[REDACTED]" if key in sensitive else value))
        args = list(record.args)
        args[2] = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), parts.fragment))
        record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(OAuthAccessLogFilter())


def is_configured() -> bool:
    return bool(
        GOOGLE_CLIENT_ID
        and GOOGLE_CLIENT_SECRET
        and GOOGLE_CLIENT_ID != GOOGLE_CLIENT_SECRET
        and GOOGLE_REDIRECT_URI
        and FRONTEND_URL
        and fernet
    )


def configuration_error() -> Optional[str]:
    if not GOOGLE_CLIENT_ID:
        return "GOOGLE_CLIENT_ID çalışma ortamında bulunamadı"
    if not GOOGLE_CLIENT_SECRET:
        return "GOOGLE_CLIENT_SECRET çalışma ortamında bulunamadı"
    if GOOGLE_CLIENT_ID == GOOGLE_CLIENT_SECRET:
        return "Google istemci sırrı geçersiz görünüyor"
    if not GOOGLE_REDIRECT_URI:
        return "GOOGLE_REDIRECT_URI çalışma ortamında bulunamadı"
    if not FRONTEND_URL:
        return "FRONTEND_URL çalışma ortamında bulunamadı"
    if not fernet:
        return "TOKEN_ENCRYPTION_KEY çalışma ortamında bulunamadı"
    return None


def client_config() -> dict:
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }
    }


def new_flow(state: Optional[str] = None) -> Flow:
    flow = Flow.from_client_config(client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    return flow


def audit_token_response(response, audit: dict):
    """Capture only safe diagnostic fields from Google's token response."""
    try:
        payload = response.json()
    except Exception:
        payload = {}
    audit.update({
        "http_status": response.status_code,
        "error": str(payload.get("error") or ""),
        "error_description": str(payload.get("error_description") or ""),
    })
    log_method = logger.error if response.status_code >= 400 else logger.info
    log_method(
        "Google token endpoint response http_status=%s error=%r error_description=%r",
        audit["http_status"],
        audit["error"][:120],
        audit["error_description"][:500],
    )
    return response


def seal(value: Optional[str]) -> Optional[str]:
    if not fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY eksik")
    return fernet.encrypt(value.encode()).decode() if value else None


def unseal(value: Optional[str]) -> Optional[str]:
    if not fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY eksik")
    return fernet.decrypt(value.encode()).decode() if value else None


async def credentials_for(db, user_id: str) -> Credentials:
    doc = await db.google_tokens.find_one({"user_id": user_id})
    if not doc or not doc.get("refresh_token"):
        raise HTTPException(409, "Google hesabı henüz bağlı değil")
    creds = Credentials(
        token=unseal(doc.get("access_token")),
        refresh_token=unseal(doc["refresh_token"]),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=doc.get("scopes", SCOPES),
    )
    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
            await db.google_tokens.update_one(
                {"user_id": user_id},
                {"$set": {
                    "access_token": seal(creds.token),
                    "expiry": creds.expiry.isoformat() if creds.expiry else None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
        except Exception as exc:
            raise HTTPException(401, "Google yetkisi süresi dolmuş; yeniden bağlanın") from exc
    return creds


def _service(api: str, version: str, creds: Credentials):
    return build(api, version, credentials=creds, cache_discovery=False)


def _http(call):
    try:
        return call.execute()
    except HttpError as e:
        raise HTTPException(e.resp.status, f"Google API hatası: {e}") from e


def _drive_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _find_drive_file(drive, name: str, mime: Optional[str] = None):
    q = f'name = {_drive_literal(name)} and trashed = false'
    if mime:
        q += f' and mimeType = {_drive_literal(mime)}'
    r = _http(drive.files().list(
        q=q, spaces="drive",
        fields="files(id,name,mimeType,modifiedTime,webViewLink)",
        pageSize=100
    ))
    return r.get("files", [])


async def is_connected(db, user_id: str) -> bool:
    doc = await db.google_tokens.find_one({"user_id": user_id})
    return bool(doc and doc.get("refresh_token"))


def _find_named_calendar(cal) -> Optional[dict]:
    page_token = None
    while True:
        result = _http(cal.calendarList().list(
            maxResults=250,
            pageToken=page_token,
            showHidden=True,
        ))
        match = next((item for item in result.get("items", []) if item.get("summary") == CALENDAR_NAME), None)
        if match:
            return match
        page_token = result.get("nextPageToken")
        if not page_token:
            return None


def _to_istanbul_iso(value: Optional[str]) -> Optional[str]:
    if not value or "T" not in value:
        return value
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(ISTANBUL_TZ).isoformat()


async def get_calendar_events_for_date(db, user_id: str, target_date: date) -> list:
    """Return a named NOVA calendar's events for one Istanbul calendar day."""
    creds = await credentials_for(db, user_id)
    cal = _service("calendar", "v3", creds)
    match = _find_named_calendar(cal)
    calendar_id = match["id"] if match else "primary"
    calendar_name = match["summary"] if match else "primary"

    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=ISTANBUL_TZ)
    day_end = day_start + timedelta(days=1)

    ev = _http(cal.events().list(
        calendarId=calendar_id,
        singleEvents=True, orderBy="startTime",
        timeMin=day_start.isoformat(), timeMax=day_end.isoformat(),
        timeZone="Europe/Istanbul",
        maxResults=50,
        fields="items(id,summary,description,start,end,location,status,htmlLink)"
    ))
    out = []
    for item in ev.get("items", []):
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
        end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
        out.append({
            "id": item.get("id"),
            "title": item.get("summary", "(başlıksız)"),
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "start": _to_istanbul_iso(start),
            "end": _to_istanbul_iso(end),
            "link": item.get("htmlLink"),
            "calendar": calendar_name,
        })
    return out


async def get_todays_calendar_events(db, user_id: str) -> list:
    local_today = datetime.now(ISTANBUL_TZ).date()
    return await get_calendar_events_for_date(db, user_id, local_today)


async def get_sheet_data(db, user_id: str):
    creds = await credentials_for(db, user_id)
    drive = _service("drive", "v3", creds)
    sheets = _service("sheets", "v4", creds)
    files = _find_drive_file(drive, SHEET_NAME, "application/vnd.google-apps.spreadsheet")
    if not files:
        return None
    sid = files[0]["id"]
    out = {}
    for tab in ["İşler", "Projeler", "Rutinler"]:
        r = _http(sheets.spreadsheets().values().get(
            spreadsheetId=sid, range=tab, majorDimension="ROWS"
        ))
        out[tab] = r.get("values", [])
    out["_meta"] = {"id": sid, "name": files[0]["name"], "link": files[0].get("webViewLink")}
    return out


async def get_drive_folder_files(db, user_id: str):
    creds = await credentials_for(db, user_id)
    drive = _service("drive", "v3", creds)
    folders = _find_drive_file(drive, DRIVE_FOLDER_NAME, "application/vnd.google-apps.folder")
    if not folders:
        return None
    folder_id = folders[0]["id"]
    q = f'{_drive_literal(folder_id)} in parents and trashed = false'
    r = _http(drive.files().list(
        q=q, spaces="drive", pageSize=100,
        fields="files(id,name,mimeType,size,modifiedTime,webViewLink)"
    ))
    return {"folder": folders[0], "files": r.get("files", [])}


async def get_core_doc_text(db, user_id: str):
    creds = await credentials_for(db, user_id)
    drive = _service("drive", "v3", creds)
    docs = _service("docs", "v1", creds)
    files = _find_drive_file(drive, DOC_NAME, "application/vnd.google-apps.document")
    if not files:
        return None
    d = _http(docs.documents().get(documentId=files[0]["id"]))
    # Extract plain text
    body = d.get("body", {}).get("content", [])
    lines = []
    for el in body:
        p = el.get("paragraph")
        if not p:
            continue
        text = ""
        for e in p.get("elements", []):
            tr = e.get("textRun")
            if tr:
                text += tr.get("content", "")
        if text.strip():
            lines.append(text.rstrip("\n"))
    return {"id": files[0]["id"], "name": files[0]["name"], "text": "\n".join(lines), "link": files[0].get("webViewLink")}


# ---------- Router ----------
def create_router(db, current_user):
    router = APIRouter(prefix="/api/google", tags=["google"])

    @router.get("/status")
    async def status(user: dict = Depends(current_user)):
        return {
            "configured": is_configured(),
            "connected": await is_connected(db, user["id"]),
            "redirect_uri": GOOGLE_REDIRECT_URI or None,
            "configuration_error": configuration_error(),
        }

    @router.get("/connect")
    async def connect(request: Request, user: dict = Depends(current_user)):
        if not is_configured():
            raise HTTPException(503, configuration_error() or "Google Cloud OAuth henüz yapılandırılmadı")
        flow = new_flow()
        # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            login_hint="yapayzekasanatcisi@gmail.com",
        )
        # Store state in DB bound to user (cookie might be stripped by Google redirect)
        await db.google_oauth_states.insert_one({
            "state": state,
            "user_id": user["id"],
            "code_verifier": seal(flow.code_verifier),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"url": url}

    @router.get("/callback")
    async def callback(request: Request):
        if not is_configured():
            raise HTTPException(503, "Google OAuth yapılandırılmadı")
        state_q = request.query_params.get("state")
        err = request.query_params.get("error")
        if err:
            return RedirectResponse(f"{FRONTEND_URL}/ayarlar?google_error={err}")
        if not state_q:
            raise HTTPException(400, "Geçersiz state")
        state_doc = await db.google_oauth_states.find_one({"state": state_q})
        if not state_doc:
            raise HTTPException(400, "Bilinmeyen state")
        user_id = state_doc["user_id"]
        created_at = datetime.fromisoformat(state_doc["created_at"])
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
            await db.google_oauth_states.delete_one({"state": state_q})
            raise HTTPException(400, "OAuth isteğinin süresi doldu")
        await db.google_oauth_states.delete_one({"state": state_q})

        code_verifier = unseal(state_doc.get("code_verifier"))
        if not code_verifier:
            logger.error("Google token exchange blocked: PKCE code_verifier missing for OAuth state")
            return RedirectResponse(f"{FRONTEND_URL}/ayarlar?google_error=pkce_verifier_missing")

        flow = new_flow(state=state_q)
        flow.code_verifier = code_verifier
        token_audit = {}
        flow.oauth2session.register_compliance_hook(
            "access_token_response",
            lambda response: audit_token_response(response, token_audit),
        )
        try:
            authorization_response = f"{GOOGLE_REDIRECT_URI}?{request.url.query}"
            flow.fetch_token(authorization_response=authorization_response)
        except Exception as exc:
            safe_failure = {
                "user_id": user_id,
                "http_status": token_audit.get("http_status"),
                "error": token_audit.get("error") or type(exc).__name__,
                "error_description": token_audit.get("error_description") or str(exc)[:500],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.google_oauth_failures.replace_one(
                {"user_id": user_id}, safe_failure, upsert=True
            )
            logger.error(
                "Google token exchange failed http_status=%s error=%r error_description=%r exception_type=%s",
                safe_failure["http_status"],
                safe_failure["error"][:120],
                safe_failure["error_description"][:500],
                type(exc).__name__,
            )
            return RedirectResponse(f"{FRONTEND_URL}/ayarlar?google_error=token_exchange_failed")
        creds = flow.credentials
        if not creds.refresh_token:
            # Preserve existing refresh_token
            old = await db.google_tokens.find_one({"user_id": user_id}) or {}
            rt = unseal(old.get("refresh_token")) if old else None
        else:
            rt = creds.refresh_token
        if not rt:
            return RedirectResponse(f"{FRONTEND_URL}/ayarlar?google_error=no_refresh_token")

        await db.google_tokens.replace_one(
            {"user_id": user_id},
            {
                "user_id": user_id,
                "access_token": seal(creds.token),
                "refresh_token": seal(rt),
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
                "scopes": list(creds.scopes) if creds.scopes else SCOPES,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            upsert=True,
        )
        await db.google_oauth_failures.delete_one({"user_id": user_id})
        return RedirectResponse(f"{FRONTEND_URL}/ayarlar?google=connected")

    @router.post("/disconnect")
    async def disconnect(user: dict = Depends(current_user)):
        await db.google_tokens.delete_one({"user_id": user["id"]})
        return {"ok": True}

    @router.get("/calendar/today")
    async def calendar_today(user: dict = Depends(current_user)):
        return {"events": await get_todays_calendar_events(db, user["id"])}

    @router.get("/calendar/date")
    async def calendar_date(date_value: date, user: dict = Depends(current_user)):
        return {"date": date_value.isoformat(), "events": await get_calendar_events_for_date(db, user["id"], date_value)}

    @router.get("/sheets")
    async def sheets_endpoint(user: dict = Depends(current_user)):
        data = await get_sheet_data(db, user["id"])
        if data is None:
            raise HTTPException(404, "'NOVA İş Merkezi' tablosu bulunamadı")
        return data

    @router.get("/drive")
    async def drive_endpoint(user: dict = Depends(current_user)):
        data = await get_drive_folder_files(db, user["id"])
        if data is None:
            raise HTTPException(404, "'NOVA ASİSTAN' klasörü bulunamadı")
        return data

    @router.get("/doc")
    async def doc_endpoint(user: dict = Depends(current_user)):
        data = await get_core_doc_text(db, user["id"])
        if data is None:
            raise HTTPException(404, "'NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler' dokümanı bulunamadı")
        return data

    @router.get("/verify")
    async def verify_workspace(user: dict = Depends(current_user)):
        target_date = date(2026, 10, 8)
        events = await get_calendar_events_for_date(db, user["id"], target_date)
        target_events = [
            event for event in events
            if event.get("calendar") == CALENDAR_NAME
            and event.get("title") == EXPECTED_CALENDAR_EVENT_TITLE
            and event.get("start", "").startswith("2026-10-08T20:00:00+03:00")
            and event.get("end", "").startswith("2026-10-08T22:00:00+03:00")
            and EXPECTED_CALENDAR_EVENT_LOCATION in event.get("location", "")
        ]
        sheet = await get_sheet_data(db, user["id"])
        if sheet is None:
            raise HTTPException(404, f"'{SHEET_NAME}' tablosu bulunamadı")
        return {
            "calendar": {
                "name": CALENDAR_NAME,
                "date": target_date.isoformat(),
                "event_found": bool(target_events),
                "events": events,
            },
            "sheets": {
                "name": SHEET_NAME,
                "file_found": True,
                "tabs": {
                    tab: {"readable": True, "row_count": len(sheet.get(tab, []))}
                    for tab in ("İşler", "Projeler", "Rutinler")
                },
            },
        }

    return router
