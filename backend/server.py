"""NOVA ASİSTAN - Backend"""
import os
import uuid
import secrets
import tempfile
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Annotated, Literal

import httpx
from fastapi import FastAPI, APIRouter, Request, Response, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from openai import AsyncOpenAI
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import google_integration as gint
from auth_middleware import SingleUserAuthorizationMiddleware
from auth_policy import ALLOWED_USER_EMAIL, AUTH_SESSION_VERSION, require_allowed_identity
from action_executor import execute_action
from assistant_context import LIVE_WEB_INTENTS, build_chat_package
from capability_registry import get_capability_registry
from connector_router import execute_read_connector
from conversation_context import save_conversation_context
from intelligence_models import answer_general_knowledge, answer_live_web
from intent_router import route_message
from personal_memory import required_memory_fact_prefix
from response_composer import apply_freshness_guard, ensure_complete_response, ensure_requested_items
from workspace_data import build_workspace_snapshot
from security import BrowserSecurityMiddleware, configured_origins, csrf_token_for_request

EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
SESSION_SECRET = os.environ['SESSION_SECRET']
AUTH_DATA_URL = os.environ['EMERGENT_AUTH_DATA_URL']

mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

serializer = URLSafeTimedSerializer(SESSION_SECRET)


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        "nova_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )

# OpenAI client via Emergent proxy for TTS/STT (universal key compatible)
openai_client = AsyncOpenAI(
    api_key=EMERGENT_LLM_KEY,
    base_url=os.environ["OPENAI_BASE_URL"]
)
NOVA_TTS_PRIMARY_VOICE = "nova"
NOVA_TTS_FALLBACK_VOICE = "marin"
NOVA_TTS_SPEED = 1.09
NOVA_TTS_STYLE = "female-executive-assistant-natural-tr"
NOVA_TTS_INSTRUCTIONS = (
    "Doğal İstanbul Türkçesiyle konuş. Sıcak, zeki ve profesyonel bir kadın yönetici asistanı gibi duyul. "
    "20’lerinin sonu ile 30’larının başında, orta perdeli bir ses kullan. Sakin ama akıcı konuş. "
    "Haber spikeri gibi ağır, çocuksu, abartılı neşeli veya robotik olma. "
    "Kelimeleri birbirinden koparma; cümle geçişlerini insan konuşması gibi bağla. "
    "Cümle aralarında yalnızca kısa ve doğal duraklamalar kullan."
)


def prepare_tts_text(value: str) -> str:
    """Remove visual citations and normalize Turkish clock speech."""
    text = re.split(r"\b(?:Kaynaklar|Sources)\s*:", value.strip(), maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s)\]>]+", "", text)
    text = re.sub(r"【[^】]+】|\[(?:\d+|cite[^\]]*)\]", "", text, flags=re.IGNORECASE)

    ones = ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
    tens = ["", "on", "yirmi", "otuz", "kırk", "elli"]

    def number_word(number: int) -> str:
        if number < 10:
            return ones[number]
        ten, one = divmod(number, 10)
        return tens[ten] + (f" {ones[one]}" if one else "")

    def spoken_time(match) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        rendered = f"saat {number_word(hour)}"
        return rendered if minute == 0 else f"{rendered} {number_word(minute)}"

    text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", spoken_time, text)
    text = re.sub(r"\bsaat\s+saat\b", "saat", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"\s*;\s*", ", ", text)
    text = re.sub(r"([.!?])\1+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()

app = FastAPI(title="NOVA ASİSTAN API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nova")


# ---------- Models ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    picture: Optional[str] = None


class SessionExchange(BaseModel):
    session_id: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(default="default", max_length=100)
    source: Literal["text", "voice"] = "text"


class TaskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    priority: str = "normal"  # 'yuksek' | 'normal' | 'dusuk'
    due_date: Optional[str] = None
    context: str = "kisisel"  # kisisel | komagene | tiyatral-nikah | bora-ai-studyo
    is_priority: bool = False  # Günün 3 önceliğinden biri mi
    completed: bool = False


class Task(TaskIn):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: str = Field(default_factory=now_iso)
    completed_at: Optional[str] = None


class NoteIn(BaseModel):
    title: Optional[str] = ""
    content: str
    category: str = "genel"  # genel | kisisel | is | fikir
    context: str = "kisisel"


class Note(NoteIn):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: str = Field(default_factory=now_iso)


class EventIn(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: str  # ISO
    end_time: Optional[str] = None
    location: Optional[str] = ""
    context: str = "kisisel"


class Event(EventIn):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: str = Field(default_factory=now_iso)


# ---------- Auth helpers ----------
async def load_current_user(request: Request) -> dict:
    token = request.cookies.get("nova_session")
    if not token:
        raise HTTPException(401, "Giriş gerekli")
    try:
        sid = serializer.loads(token, max_age=60 * 60 * 24 * 7)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Oturum geçersiz veya süresi dolmuş")
    sess = await db.sessions.find_one({"session_id": sid}, {"_id": 0})
    if not sess:
        raise HTTPException(401, "Oturum bulunamadı")
    if sess.get("auth_version") != AUTH_SESSION_VERSION:
        await db.sessions.delete_one({"session_id": sid})
        raise HTTPException(401, "Oturum yenilenmeli")
    user = await db.users.find_one({"id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Kullanıcı bulunamadı")
    try:
        require_allowed_identity(user)
    except HTTPException:
        await db.sessions.delete_one({"session_id": sid})
        raise
    return user


async def current_user(request: Request) -> dict:
    authorized_user = getattr(request.state, "authorized_user", None)
    if authorized_user:
        return authorized_user
    return await load_current_user(request)


# ---------- Auth routes ----------
@api.post("/auth/session")
async def auth_session(payload: SessionExchange, response: Response):
    """Exchange Emergent session_id for a user and local cookie."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            AUTH_DATA_URL,
            headers={"X-Session-ID": payload.session_id}
        )
    if r.status_code != 200:
        raise HTTPException(401, "Google oturumu doğrulanamadı")
    data = r.json()

    try:
        email = require_allowed_identity(data)
    except HTTPException as exc:
        denied = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        denied.delete_cookie("nova_session", path="/", samesite="lax", secure=True)
        return denied
    user_id = data.get("id") or data.get("email")
    user_doc = {
        "id": user_id,
        "email": email,
        "email_verified": True,
        "name": data.get("name"),
        "picture": data.get("picture"),
        "updated_at": now_iso(),
    }
    await db.users.update_one({"id": user_id}, {"$set": user_doc}, upsert=True)

    local_sid = secrets.token_urlsafe(32)
    await db.sessions.insert_one({
        "session_id": local_sid,
        "user_id": user_id,
        "auth_version": AUTH_SESSION_VERSION,
        "created_at": now_iso(),
    })
    token = serializer.dumps(local_sid)
    set_session_cookie(response, token)
    return User(**user_doc).model_dump()


@api.get("/auth/me")
async def auth_me(user: Annotated[dict, Depends(current_user)]):
    return User(**user).model_dump()


@api.get("/auth/csrf")
async def auth_csrf(request: Request, user: Annotated[dict, Depends(current_user)]):
    try:
        return JSONResponse(
            {"csrf_token": csrf_token_for_request(request)},
            headers={"Cache-Control": "no-store"},
        )
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Oturum geçersiz veya süresi dolmuş")


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("nova_session")
    if token:
        try:
            sid = serializer.loads(token)
            await db.sessions.delete_one({"session_id": sid})
        except BadSignature:
            pass
    response.delete_cookie("nova_session", path="/", samesite="lax", secure=True)
    return {"ok": True}


# ---------- Context prompt builder ----------
TR_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def today_turkish_facts():
    """Return objective date facts only."""
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    weekday_name = TR_WEEKDAYS[now.weekday()]
    day = now.day
    month_name = TR_MONTHS[now.month - 1]
    year = now.year
    return {
        "weekday": weekday_name,
        "date_str": f"{day} {month_name} {year} {weekday_name}",
        "iso": now.strftime("%Y-%m-%d"),
    }


async def build_system_prompt(
    user: dict,
    google_calendar_summary: str = "",
    google_workspace_summary: str = "",
) -> str:
    """Build NOVA's persona + current context from user data."""
    name = user.get("name", "Bora")
    facts = today_turkish_facts()

    tasks = await db.tasks.find(
        {"user_id": user["id"], "completed": False},
        {"_id": 0}
    ).to_list(50)
    local_events = await db.events.find(
        {"user_id": user["id"], "start_time": {"$gte": facts["iso"], "$lt": facts["iso"] + "T23:59:59"}},
        {"_id": 0}
    ).sort("start_time", 1).to_list(50)

    pending = "\n".join(
        f"- [{t.get('priority','normal').upper()}] {t['title']} ({t.get('context','')})"
        for t in tasks[:15]
    ) or "YOK"

    local_events_summary = "\n".join(
        f"- {e['start_time'][11:16]} {e['title']} ({e.get('location','') or 'konum belirtilmemiş'})"
        for e in local_events[:15]
    ) or "YOK"

    gc_block = google_calendar_summary.strip() if google_calendar_summary.strip() else "GOOGLE_TAKVIM_BAGLI_DEGIL"
    workspace_block = google_workspace_summary.strip() if google_workspace_summary.strip() else "GOOGLE_WORKSPACE_BAGLI_DEGIL"

    return f"""Sen NOVA ASİSTAN'sın — Bora'nın kişisel özel sekreteri.

KİMLİK: Türkçe konuşursun. Bora diye hitap edersin; "Bora Bey" deme. Tonun doğal, sıcak, sakin ve profesyonel bir özel sekreter gibidir. Robotik kapanışlar kullanma. Cevapların kısa, net ve aksiyon odaklıdır.

BUGÜN: {facts['date_str']}

── KESİN KURALLAR (BUNA UY) ──
1) ASLA bilgi uydurma. Sadece aşağıda GERÇEK VERİ olarak verilen bilgileri kullan.
2) Bir veri alanı YOK veya GOOGLE_TAKVIM_BAGLI_DEGIL diyorsa, "bu bilgi henüz bağlı değil / sistemde yok" de — tahmin etme, örnek verme.
3) Komagene rutinlerini yalnızca GOOGLE WORKSPACE GERÇEK VERİ bölümünde bulunuyorsa söyle.
4) Takvim etkinliklerini sadece aşağıda yazdığı saat ve isimle söyle. Saat uydurma.
5) Bekleyen işleri sadece aşağıdaki listede varsa söyle.
6) Bir tarih, rutin veya görev aşağıdaki gerçek veri alanlarında yoksa onu söyleme.

── GOOGLE TAKVİM İSTENEN DÖNEM (gerçek) ──
{gc_block}

── GOOGLE WORKSPACE GERÇEK VERİ ──
{workspace_block}

── UYGULAMA İÇİ YEREL ETKİNLİKLER BUGÜN ──
{local_events_summary}

── BEKLEYEN İŞLER ──
{pending}

GÜVENLİK: Onay almadan ödeme/rezervasyon/mail/etkinlik silme yapma."""


# ---------- Chat ----------
async def _google_calendar_summary_for_prompt(user: dict) -> str:
    """Fetch today's Google Calendar events for the prompt; return empty if not connected."""
    try:
        if not gint.is_configured():
            return "GOOGLE_OAUTH_YAPILANDIRILMADI"
        if not await gint.is_connected(db, user["id"]):
            return "GOOGLE_TAKVIM_BAGLI_DEGIL"
        events = await gint.get_todays_calendar_events(db, user["id"])
        if not events:
            return "Bugün için Google Takvim'de etkinlik YOK."
        lines = []
        for e in events:
            start = e.get("start", "")
            # Extract HH:MM if datetime, else "Tüm gün"
            time_str = "Tüm gün"
            if "T" in start:
                time_str = start[11:16]
            loc = f" — {e['location']}" if e.get("location") else ""
            lines.append(f"- {time_str} {e['title']}{loc} [takvim: {e.get('calendar','')}]")
        return "\n".join(lines)
    except HTTPException:
        return "GOOGLE_TAKVIM_HATASI"
    except Exception as exc:
        logger.error("Google calendar fetch failed type=%s", type(exc).__name__)
        return "GOOGLE_TAKVIM_HATASI"


async def _google_workspace_summary_for_prompt(user: dict) -> str:
    """Read real Sheets/Docs context; never substitute sample data."""
    if not gint.is_configured() or not await gint.is_connected(db, user["id"]):
        return "GOOGLE_WORKSPACE_BAGLI_DEGIL"
    sections = []
    try:
        sheet = await gint.get_sheet_data(db, user["id"])
        if sheet:
            for tab in ("İşler", "Projeler", "Rutinler"):
                rows = sheet.get(tab, [])
                rendered = "\n".join(" | ".join(map(str, row)) for row in rows[:30])
                sections.append(f"{tab}:\n{rendered or 'VERİ YOK'}")
        else:
            sections.append("NOVA İş Merkezi: DOSYA BULUNAMADI")
    except Exception as exc:
        logger.error("Google sheets fetch failed type=%s", type(exc).__name__)
        sections.append("NOVA İş Merkezi: OKUMA HATASI")
    try:
        doc = await gint.get_core_doc_text(db, user["id"])
        sections.append(f"Çekirdek Kurallar:\n{doc['text'][:12000]}" if doc else "Çekirdek Kurallar: DOSYA BULUNAMADI")
    except Exception as exc:
        logger.error("Google docs fetch failed type=%s", type(exc).__name__)
        sections.append("Çekirdek Kurallar: OKUMA HATASI")
    return "\n\n".join(sections)


def _data_source_label(package: dict) -> str:
    intent = package.get("intent", "general")
    labels = {
        "personal_memory": "Personal Memory",
        "unknown_fallback": "Unknown Fallback",
        "conversation_context": "Conversation Context",
        "general": "General LLM",
        "briefing": "Calendar + Workspace",
        "today_schedule": "Calendar + Workspace",
        "calendar_date_query": "Calendar",
        "pending_tasks": "Workspace",
        "weekly_priorities": "Calendar + Workspace Priority Engine",
        "weekly_routines": "Workspace Routines",
        "week_overview": "Calendar + Workspace",
        "hotel_search": "Hotels.com + Official Hotel Sources",
        "restaurant_search": "Live Restaurant Search",
        "cinema_search": "Cinetime + Live Cinema Search",
        "event_search": "Official Event Sources + Live Web Search",
        "leisure_search": "Live City Planning Sources",
        "shopping_search": "Provider-targeted Shopping Search",
        "planning": "General LLM + Personal Memory Context",
        "personal_work": "Calendar + Google Sheets Personal Work",
        "availability": "Google Calendar · Availability",
        "drive_read": "Google Drive",
        "docs_read": "Google Docs",
        "sheets_read": "Google Sheets",
        "gmail_read": "Capability Registry",
        "meta": "Conversation",
    }
    if intent == "web_search":
        return "Calendar + Web Search" if package.get("web_context") else "Web Search"
    if intent in {"hotel_search", "restaurant_search", "cinema_search", "event_search", "leisure_search", "shopping_search"}:
        return ("Calendar + " if package.get("web_context") else "") + labels[intent]
    if intent == "travel_search":
        return "Calendar/Workspace + Web Search + Travel Profile" if package.get("web_context") else "Web Search + Travel Profile"
    return labels.get(intent, "General LLM")


@api.post("/chat")
async def chat(body: ChatIn, user: Annotated[dict, Depends(current_user)]):
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    decision = route_message(body.message, now)
    special_result = None
    action_result = None
    registry = None
    try:
        special_intents = {"meta", "drive_read", "docs_read", "sheets_read", "gmail_read", "personal_work", "availability"}
        if decision.intent in special_intents or decision.action:
            registry = await get_capability_registry(db, user["id"])
        if decision.action:
            action = await execute_action(decision, registry or {})
            action_result = action.as_dict()
            special_result = {"reply": action.reply, "source": "Capability Registry + Action Executor", "events": []}
        elif decision.intent in special_intents:
            special_result = await execute_read_connector(decision, body.message, db, user["id"], registry or {})
        if special_result:
            package = {
                "intent": decision.intent,
                "target_date": decision.target_date.isoformat() if decision.target_date else None,
                "calendar_summary": "",
                "workspace_summary": "",
                "reply": special_result["reply"],
                "prior_context": "",
                "web_context": "",
                "events": special_result.get("events", []),
                "connector": decision.connector,
                "requested_items": decision.requested_items,
                "data_source_override": special_result["source"],
            }
        else:
            package = await build_chat_package(
                db,
                user["id"],
                body.message,
                conversation_id=body.conversation_id,
                route_decision=decision,
            )
    except Exception as exc:
        logger.error("Real-time conversation context failed type=%s", type(exc).__name__)
        connector_failure = bool(decision.action or decision.connector in {"calendar", "sheets", "drive", "docs", "gmail", "workspace"})
        package = {
            "intent": decision.intent if connector_failure else "general",
            "calendar_summary": "GOOGLE_TAKVIM_HATASI",
            "workspace_summary": "GOOGLE_WORKSPACE_HATASI",
            "reply": "Bora, şu anda ilgili bağlantıdan sonuç alamıyorum." if connector_failure else None,
            "prior_context": "",
            "web_context": "",
            "events": [],
            "connector": decision.connector,
            "requested_items": decision.requested_items,
        }
    session_id = f'{user["id"]}:{body.conversation_id}'
    answer = package.get("reply")
    sources = []
    if not answer:
        try:
            if package.get("intent") in LIVE_WEB_INTENTS:
                answer, sources = await answer_live_web(
                    body.message,
                    session_id,
                    intent=package.get("intent", "web_search"),
                    workspace_context=package.get("web_context", ""),
                    prior_context=package.get("prior_context", ""),
                )
            else:
                answer = await answer_general_knowledge(
                    body.message,
                    session_id,
                    prior_context=package.get("prior_context", ""),
                )
        except Exception as exc:
            logger.error("Chat provider error type=%s", type(exc).__name__)
            raise HTTPException(500, "NOVA şu anda yanıt veremiyor")
    if package.get("intent") in LIVE_WEB_INTENTS:
        current_sensitive = any(term in body.message.casefold() for term in ("fiyat", "ücret", "tarife", "maliyet", "güncel"))
        target_year = decision.target_date.year if decision.target_date else now.year
        answer = apply_freshness_guard(answer, target_year, current_sensitive)
        answer = ensure_requested_items(answer, decision.requested_items)
    if package.get("intent") == "planning":
        prefix = required_memory_fact_prefix(decision.memory_context_keys)
        if prefix and prefix not in answer:
            answer = f"{prefix} {answer}"
    answer = ensure_complete_response(answer)

    # Save to conversation history
    await db.messages.insert_one({
        "user_id": user["id"],
        "conversation_id": body.conversation_id,
        "role": "user",
        "content": body.message,
        "source": body.source,
        "created_at": now_iso(),
    })
    await db.messages.insert_one({
        "user_id": user["id"],
        "conversation_id": body.conversation_id,
        "role": "assistant",
        "content": answer,
        "source": body.source,
        "sources": sources,
        "created_at": now_iso(),
    })

    await save_conversation_context(
        db,
        user["id"],
        body.conversation_id,
        body.message,
        answer,
        package,
        sources=sources,
    )

    return {
        "answer": answer,
        "intent": package.get("intent", "general"),
        "data_source": package.get("data_source_override") or _data_source_label(package),
        "sources": sources,
        "source": body.source,
        "action_result": action_result,
        "resolved_target_date": package.get("target_date"),
    }


@api.get("/capabilities")
async def capabilities(user: Annotated[dict, Depends(current_user)]):
    return await get_capability_registry(db, user["id"], force=True)


@api.get("/chat/history")
async def chat_history(user: Annotated[dict, Depends(current_user)], conversation_id: str = "default"):
    msgs = await db.messages.find(
        {"user_id": user["id"], "conversation_id": conversation_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return msgs


# ---------- Daily briefing ----------
@api.get("/briefing/today")
async def briefing_today(user: Annotated[dict, Depends(current_user)]):
    """Return the same real-data briefing used by text and voice commands."""
    today = datetime.now(ZoneInfo("Europe/Istanbul"))
    today_str = today.strftime("%Y-%m-%d")

    # Local app events
    local_events = await db.events.find({
        "user_id": user["id"],
        "start_time": {"$gte": today_str, "$lt": today_str + "T23:59:59"}
    }, {"_id": 0}).sort("start_time", 1).to_list(50)

    tasks = await db.tasks.find({
        "user_id": user["id"], "completed": False
    }, {"_id": 0}).to_list(50)
    priorities = [t for t in tasks if t.get("is_priority")]

    google_connected = gint.is_configured() and await gint.is_connected(db, user["id"])
    try:
        package = await build_chat_package(db, user["id"], "günün brifingi", intent_override="briefing")
        text = package["reply"]
        google_events = package["events"]
    except Exception as exc:
        logger.error("Briefing error type=%s", type(exc).__name__)
        text = "Günaydın Bora. Brifing şu anda güvenli biçimde üretilemedi."
        google_events = []

    return {
        "text": text,
        "events": local_events,
        "google_events": google_events,
        "google_connected": google_connected,
        "google_configured": gint.is_configured(),
        "priorities": priorities,
        "pending_count": package.get("pending_count", 0) if "package" in locals() else 0,
        "date": today.strftime("%d %B %Y, %A"),
    }


@api.get("/workspace/snapshot")
async def workspace_snapshot(user: Annotated[dict, Depends(current_user)]):
    """Single normalized Google Calendar/Sheets view model for every app page."""
    return await build_workspace_snapshot(db, user["id"])


# ---------- Tasks CRUD ----------
@api.post("/tasks", response_model=Task)
async def create_task(body: TaskIn, user: Annotated[dict, Depends(current_user)]):
    t = Task(user_id=user["id"], **body.model_dump())
    await db.tasks.insert_one(t.model_dump())
    return t


@api.get("/tasks", response_model=List[Task])
async def list_tasks(user: Annotated[dict, Depends(current_user)], context: Optional[str] = None, completed: Optional[bool] = None):
    q = {"user_id": user["id"]}
    if context: q["context"] = context
    if completed is not None: q["completed"] = completed
    rows = await db.tasks.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@api.patch("/tasks/{task_id}")
async def update_task(task_id: str, body: dict, user: Annotated[dict, Depends(current_user)]):
    update = {k: v for k, v in body.items() if k in {"title", "description", "priority", "due_date", "context", "is_priority", "completed"}}
    if update.get("completed"):
        update["completed_at"] = now_iso()
    r = await db.tasks.update_one({"id": task_id, "user_id": user["id"]}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(404, "İş bulunamadı")
    doc = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    return doc


@api.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: Annotated[dict, Depends(current_user)]):
    r = await db.tasks.delete_one({"id": task_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "İş bulunamadı")
    return {"ok": True}


# ---------- Notes CRUD ----------
@api.post("/notes", response_model=Note)
async def create_note(body: NoteIn, user: Annotated[dict, Depends(current_user)]):
    n = Note(user_id=user["id"], **body.model_dump())
    await db.notes.insert_one(n.model_dump())
    return n


@api.get("/notes", response_model=List[Note])
async def list_notes(user: Annotated[dict, Depends(current_user)], context: Optional[str] = None):
    q = {"user_id": user["id"]}
    if context: q["context"] = context
    rows = await db.notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows


@api.delete("/notes/{note_id}")
async def delete_note(note_id: str, user: Annotated[dict, Depends(current_user)]):
    r = await db.notes.delete_one({"id": note_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Not bulunamadı")
    return {"ok": True}


# ---------- Events CRUD ----------
@api.post("/events", response_model=Event)
async def create_event(body: EventIn, user: Annotated[dict, Depends(current_user)]):
    e = Event(user_id=user["id"], **body.model_dump())
    await db.events.insert_one(e.model_dump())
    return e


@api.get("/events", response_model=List[Event])
async def list_events(user: Annotated[dict, Depends(current_user)], start: Optional[str] = None, end: Optional[str] = None):
    q = {"user_id": user["id"]}
    if start and end:
        q["start_time"] = {"$gte": start, "$lte": end}
    rows = await db.events.find(q, {"_id": 0}).sort("start_time", 1).to_list(500)
    return rows


@api.delete("/events/{event_id}")
async def delete_event(event_id: str, user: Annotated[dict, Depends(current_user)]):
    r = await db.events.delete_one({"id": event_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Etkinlik bulunamadı")
    return {"ok": True}


# ---------- STT ----------
@api.post("/voice/stt")
async def stt(file: UploadFile = File(...), user: dict = Depends(current_user)):
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Ses dosyası 25 MB'tan büyük olamaz")
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(raw)
            path = f.name
        with open(path, "rb") as audio_file:
            tr = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="tr"
            )
        return {"text": tr.text}
    except Exception as exc:
        logger.error("STT provider error type=%s", type(exc).__name__)
        raise HTTPException(500, "Ses şu anda metne çevrilemedi")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


# ---------- TTS ----------
@api.post("/voice/tts")
async def tts(text: str = Form(...), user: dict = Depends(current_user)):
    if not text.strip() or len(text) > 4000:
        raise HTTPException(400, "Metin boş veya çok uzun")
    try:
        prepared_text = prepare_tts_text(text)
        voice_used = NOVA_TTS_PRIMARY_VOICE
        try:
            resp = await openai_client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=voice_used,
                input=prepared_text,
                instructions=NOVA_TTS_INSTRUCTIONS,
                speed=NOVA_TTS_SPEED,
                response_format="mp3"
            )
        except Exception as primary_error:
            logger.warning("Primary TTS voice failed; using marin fallback: %s", type(primary_error).__name__)
            voice_used = NOVA_TTS_FALLBACK_VOICE
            resp = await openai_client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=voice_used,
                input=prepared_text,
                instructions=NOVA_TTS_INSTRUCTIONS,
                speed=NOVA_TTS_SPEED,
                response_format="mp3"
            )
        audio_bytes = resp.read() if hasattr(resp, 'read') else resp.content
        return StreamingResponse(
            iter([audio_bytes]),
            media_type="audio/mpeg",
            headers={
                "X-Nova-Voice": voice_used,
                "X-Nova-Voice-Primary": NOVA_TTS_PRIMARY_VOICE,
                "X-Nova-Voice-Fallback": NOVA_TTS_FALLBACK_VOICE,
                "X-Nova-Voice-Speed": str(NOVA_TTS_SPEED),
                "X-Nova-Voice-Style": NOVA_TTS_STYLE,
                "X-Nova-TTS-Mode": "single-request",
            },
        )
    except Exception as exc:
        logger.error("TTS provider error type=%s", type(exc).__name__)
        raise HTTPException(500, "Ses şu anda üretilemedi")


# ---------- Root ----------
@api.get("/")
async def root():
    return {"message": "NOVA ASİSTAN API", "status": "online"}


app.include_router(api)
app.include_router(gint.create_router(db, current_user))
allowed_origins = configured_origins()
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=sorted(allowed_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-CSRF-Token"],
)
app.add_middleware(SingleUserAuthorizationMiddleware, current_user_loader=load_current_user)
app.add_middleware(BrowserSecurityMiddleware, session_secret=SESSION_SECRET, allowed_origins=allowed_origins)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled server error path=%s type=%s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Beklenmeyen sunucu hatası"})


@app.on_event("startup")
async def enforce_single_user_store():
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1}).to_list(10000)
    allowed_user_ids = [
        user["id"]
        for user in users
        if user.get("id") and str(user.get("email", "")).strip().casefold() == ALLOWED_USER_EMAIL
    ]
    unauthorized_user_ids = [
        user["id"] for user in users if user.get("id") and user["id"] not in allowed_user_ids
    ]

    sessions = await db.sessions.delete_many({
        "$or": [
            {"auth_version": {"$ne": AUTH_SESSION_VERSION}},
            {"user_id": {"$nin": allowed_user_ids}},
        ]
    })
    tokens = await db.google_tokens.delete_many({"user_id": {"$nin": allowed_user_ids}})
    await db.google_oauth_states.delete_many({})
    users_deleted = 0
    if unauthorized_user_ids:
        result = await db.users.delete_many({"id": {"$in": unauthorized_user_ids}})
        users_deleted = result.deleted_count
    logger.warning(
        "Single-user startup enforcement sessions_deleted=%s users_deleted=%s tokens_deleted=%s",
        sessions.deleted_count,
        users_deleted,
        tokens.deleted_count,
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    mongo_client.close()
