"""NOVA ASİSTAN - Backend"""
import os
import uuid
import secrets
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Annotated

import httpx
from fastapi import FastAPI, APIRouter, Request, Response, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from emergentintegrations.llm.chat import LlmChat, UserMessage
from openai import AsyncOpenAI

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
SESSION_SECRET = os.environ['SESSION_SECRET']
AUTH_DATA_URL = os.environ['EMERGENT_AUTH_DATA_URL']

mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

serializer = URLSafeTimedSerializer(SESSION_SECRET)

# OpenAI client via Emergent proxy for TTS/STT (universal key compatible)
openai_client = AsyncOpenAI(
    api_key=EMERGENT_LLM_KEY,
    base_url="https://integrations.emergentagent.com/llm"
)

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
async def current_user(request: Request) -> dict:
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
    user = await db.users.find_one({"id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "Kullanıcı bulunamadı")
    return user


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

    user_id = data.get("id") or data.get("email")
    user_doc = {
        "id": user_id,
        "email": data.get("email"),
        "name": data.get("name"),
        "picture": data.get("picture"),
        "updated_at": now_iso(),
    }
    await db.users.update_one({"id": user_id}, {"$set": user_doc}, upsert=True)

    local_sid = secrets.token_urlsafe(32)
    await db.sessions.insert_one({
        "session_id": local_sid,
        "user_id": user_id,
        "created_at": now_iso(),
    })
    token = serializer.dumps(local_sid)
    response.set_cookie(
        "nova_session", token,
        httponly=True, secure=True, samesite="none",
        max_age=60 * 60 * 24 * 7, path="/"
    )
    return User(**user_doc).model_dump()


@api.get("/auth/me")
async def auth_me(user: Annotated[dict, Depends(current_user)]):
    return User(**user).model_dump()


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    token = request.cookies.get("nova_session")
    if token:
        try:
            sid = serializer.loads(token)
            await db.sessions.delete_one({"session_id": sid})
        except BadSignature:
            pass
    response.delete_cookie("nova_session", path="/", samesite="none", secure=True)
    return {"ok": True}


# ---------- Context prompt builder ----------
async def build_system_prompt(user: dict) -> str:
    """Build NOVA's persona + current context from user data."""
    name = user.get("name", "Bora")
    today = datetime.now(timezone.utc).strftime("%d.%m.%Y %A")
    # Pull a lightweight context snapshot
    tasks = await db.tasks.find(
        {"user_id": user["id"], "completed": False},
        {"_id": 0}
    ).to_list(50)
    events_today = await db.events.find(
        {"user_id": user["id"]},
        {"_id": 0}
    ).to_list(50)

    pending = "\n".join(
        f"- [{t.get('priority','normal').upper()}] {t['title']} ({t.get('context','')})"
        for t in tasks[:15]
    ) or "(bekleyen iş yok)"

    events_summary = "\n".join(
        f"- {e['start_time'][:16].replace('T',' ')} - {e['title']} ({e.get('location','') or 'konum yok'})"
        for e in events_today[:15]
    ) or "(takvim boş)"

    return f"""Sen NOVA ASİSTAN'sın — Bora Bey'in kişisel özel sekreteri ve yapay zekâ yöneticisisin.

KİMLİK:
- Adın NOVA. Her zaman Türkçe konuşursun.
- Tonun: sıcak, sakin, saygılı, profesyonel. Robotik DEĞİL.
- Bora Bey'e saygılı hitap edersin ("Bora Bey", "siz" gibi) ama resmi kalmazsın.
- Cevapların kısa, net ve aksiyon odaklıdır. Gereksiz uzatma.
- Teknik İngilizce terimleri kullanmazsın.

KULLANICI: {name}
BUGÜN: {today}

BORA BEY'İN HAYATI (bağlam):
- İşletme: Komagene (çiğköfte zinciri, 11:00-02:00 çalışır). Her ayın 15'i %50 bedava çiğköfte günü, 14'ü hazırlık (balon+afiş). Salı+Cuma 16:00'a kadar merkez siparişi, Çarşamba+Cumartesi sevkiyat gelir.
- İş: Tiyatral Nikâh organizasyonları (şehir dışı seyahatler sık).
- İş: Bora AI Stüdyo — Ekim 2026 planı: Avin Zerin, Korkut Erdağ, Grup Karadüş için ayda 2 şarkı. Aktif: Kadına Şiddet Serisi, Grup Karadüş klibi, sırada Çocuk İstismarı projesi.
- Özel: Tuğba (eş/sevgili) doğum günü 10 Kasım 1990 — ASLA unutma, önceden hatırlat. Sürprizleri ortak takvime YAZMA.
- Önemli günler: Bora 12 Mayıs, Anne 13 Temmuz, Tolga (abi) 29 Temmuz, Atakan 11 Ocak, 14 Şubat Sevgililer, 8 Mart Kadınlar Günü.
- Yemek: Fast food, köfte, et, pizza (sebzesiz, mayonezsiz). İçecek: Coca-Cola. Enerji: Red Bull, Tadelle+soğuk su.
- Ulaşım: Fiat Egea; yakın yollara özel araç, orta mesafe otobüs (en ön tekli koltuk tercih), uzağa uçak/otobüs karşılaştır.
- Otel: Orduevi > ekonomik 3+ yıldız, kahvaltı dahil.
- Çalışma düzeni: Uyanış 08-12 arası, dükkânda 19'da, kapanış 02, uyku 04.

GÜVENLİK:
- Onay almadan ödeme yapma, bilet alma, rezervasyon kesinleştirme, önemli mail gönderme, etkinlik silme.
- Önce öneri sun, sonra onay iste.

BUGÜNKÜ TAKVİM:
{events_summary}

BEKLEYEN İŞLER:
{pending}

Yanıtların doğal akışlı Türkçe olsun. Liste veririsen kısa ve okunabilir olsun."""


# ---------- Chat ----------
@api.post("/chat")
async def chat(body: ChatIn, user: Annotated[dict, Depends(current_user)]):
    system_prompt = await build_system_prompt(user)
    session_id = f'{user["id"]}:{body.conversation_id}'
    try:
        client = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("openai", "gpt-4o-mini").with_params(temperature=0.5, max_tokens=800)
        answer = await client.send_message(UserMessage(text=body.message))
    except Exception as e:
        logger.exception("Chat error")
        raise HTTPException(500, f"NOVA yanıt veremedi: {str(e)}")

    # Save to conversation history
    await db.messages.insert_one({
        "user_id": user["id"],
        "conversation_id": body.conversation_id,
        "role": "user",
        "content": body.message,
        "created_at": now_iso(),
    })
    await db.messages.insert_one({
        "user_id": user["id"],
        "conversation_id": body.conversation_id,
        "role": "assistant",
        "content": answer,
        "created_at": now_iso(),
    })

    return {"answer": answer}


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
    """Generate NOVA's natural-sounding today briefing."""
    today = datetime.now(timezone.utc)
    today_str = today.strftime("%Y-%m-%d")

    events = await db.events.find({
        "user_id": user["id"],
        "start_time": {"$gte": today_str, "$lt": today_str + "T23:59:59"}
    }, {"_id": 0}).sort("start_time", 1).to_list(50)

    tasks = await db.tasks.find({
        "user_id": user["id"], "completed": False
    }, {"_id": 0}).to_list(50)

    priorities = [t for t in tasks if t.get("is_priority")]

    system_prompt = await build_system_prompt(user)
    prompt = (
        "Bugünün brifingini ver. Sade bir sekreter tonuyla, 3-5 cümle, "
        "madde listesi değil akıcı paragraf şeklinde. 'Günaydın Bora Bey' ile başla. "
        "Bugünkü sabit programları, kritik saatleri ve günün önemli işlerini birleştir."
    )
    try:
        client = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f'{user["id"]}:briefing-{today_str}',
            system_message=system_prompt
        ).with_model("openai", "gpt-4o-mini").with_params(temperature=0.4, max_tokens=400)
        text = await client.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("Briefing error")
        text = f"Günaydın Bora Bey. Bugün için bilgi alınamadı: {str(e)}"

    return {
        "text": text,
        "events": events,
        "priorities": priorities,
        "pending_count": len([t for t in tasks if not t.get("is_priority")]),
        "date": today.strftime("%d %B %Y, %A"),
    }


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
    except Exception as e:
        logger.exception("STT error")
        raise HTTPException(500, f"Ses metne çevrilemedi: {str(e)}")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


# ---------- TTS ----------
@api.post("/voice/tts")
async def tts(text: str = Form(...), user: dict = Depends(current_user)):
    if not text.strip() or len(text) > 4000:
        raise HTTPException(400, "Metin boş veya çok uzun")
    try:
        resp = await openai_client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            response_format="mp3"
        )
        audio_bytes = resp.read() if hasattr(resp, 'read') else resp.content
        return StreamingResponse(iter([audio_bytes]), media_type="audio/mpeg")
    except Exception as e:
        logger.exception("TTS error")
        raise HTTPException(500, f"Ses üretilemedi: {str(e)}")


# ---------- Root ----------
@api.get("/")
async def root():
    return {"message": "NOVA ASİSTAN API", "status": "online"}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    mongo_client.close()
