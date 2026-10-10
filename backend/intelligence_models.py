"""Cost-aware general knowledge and grounded live web research services."""
from datetime import datetime
import logging
import os
import re

from emergentintegrations.llm.chat import LlmChat, UserMessage

import google_integration as gint
from date_resolver import fold_turkish
from personal_memory import profile_context_for_web


WEB_FAILURE = "Bu bilgiyi canlı kaynaktan doğrulayamadım, Bora."
logger = logging.getLogger("nova.intelligence")

SOURCE_MATRIX = {
    "hotel_search": "Önce Hotels.com, sonra otelin resmi sitesi; yalnız gerçek otel kullan.",
    "restaurant_search": "Önce resmi mekan/menu bilgisi ve Yemeksepeti; gerçek çalışma saati ve menü doğrula.",
    "cinema_search": "Önce Cinetime ÖzdilekPark Nilüfer resmi programı; yoksa diğer gerçek Bursa sinemaları.",
    "event_search": "Önce resmi mekan, organizatör veya bilet platformu; gerçek tarih ve saat zorunlu.",
    "leisure_search": "Gerçek mekanların resmi sayfaları ve güncel etkinlik kaynaklarıyla plan yap.",
}


def _annotation_sources(raw, content: str = "") -> list[dict]:
    try:
        annotations = getattr(raw.choices[0].message, "annotations", None) or []
    except Exception:
        annotations = []
    sources = []
    for annotation in annotations:
        data = annotation.model_dump() if hasattr(annotation, "model_dump") else annotation
        if not isinstance(data, dict):
            continue
        citation = data.get("url_citation") or data
        url = citation.get("url") if isinstance(citation, dict) else None
        if not url or any(item["url"] == url for item in sources):
            continue
        sources.append({"title": citation.get("title") or "Kaynak", "url": url})
    if sources:
        return sources[:5]
    try:
        choice = raw.choices[0]
        metadata = getattr(choice, "grounding_metadata", None) or getattr(choice, "groundingMetadata", None)
        if hasattr(metadata, "model_dump"):
            metadata = metadata.model_dump()
        chunks = (metadata or {}).get("groundingChunks", []) if isinstance(metadata, dict) else []
        for chunk in chunks:
            web = chunk.get("web", {}) if isinstance(chunk, dict) else {}
            url = web.get("uri")
            if url and not any(item["url"] == url for item in sources):
                sources.append({"title": web.get("title") or "Kaynak", "url": url})
    except Exception:
        pass

    def walk(value):
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, dict):
            url = value.get("url") or value.get("uri")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                title = value.get("title") or value.get("name") or "Kaynak"
                if not any(item["url"] == url for item in sources):
                    sources.append({"title": str(title), "url": url})
            for nested in value.values():
                walk(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                walk(nested)

    try:
        walk(raw)
    except Exception:
        pass
    if not sources and content:
        for url in re.findall(r"https?://[^\s)\]>]+", content):
            cleaned = url.rstrip(".,;:")
            if not any(item["url"] == cleaned for item in sources):
                sources.append({"title": "Kaynak", "url": cleaned})
    return sources[:5]


def _required_source_domains(folded: str) -> list[str]:
    """Domains explicitly required by the user's request."""
    rules = (
        ("mediamarkt", "mediamarkt"),
        ("hepsiburada", "hepsiburada"),
        ("trendyol", "trendyol"),
        ("hotels.com", "hotels"),
        ("obilet", "obilet"),
        ("flypgs", "flypgs"),
        ("pegasus", "flypgs"),
        ("turkishairlines", "turkishairlines"),
        ("thy", "turkishairlines"),
        ("ajet", "ajet"),
        ("tcdd", "tcdd"),
        ("budo", "budo"),
        ("ido", "ido"),
        ("cinetime", "cinetime"),
        ("yemeksepeti", "yemeksepeti"),
    )
    return [domain for marker, domain in rules if marker in folded]


def _sources_satisfy_request(sources: list[dict], folded: str) -> bool:
    required = _required_source_domains(folded)
    if not required:
        return bool(sources)
    urls = " ".join(str(item.get("url", "")).lower() for item in sources)
    return all(domain in urls for domain in required)


def _finish_reason(raw) -> str:
    """Return provider finish reason without assuming one SDK response shape."""
    try:
        choice = raw.choices[0]
        reason = getattr(choice, "finish_reason", None)
        if reason is None and hasattr(choice, "model_dump"):
            reason = choice.model_dump().get("finish_reason")
        return str(reason or "").lower()
    except Exception:
        return ""


def _looks_truncated(answer: str, raw) -> bool:
    """Detect provider token-limit truncation and obvious long unfinished output."""
    reason = _finish_reason(raw)
    if any(marker in reason for marker in ("length", "max_token", "max_output")):
        return True

    text = (answer or "").rstrip()
    if not text or len(text) < 1200:
        return False

    return not text.endswith((".", "!", "?", ")", "]"))


def _render_sources(answer: str, sources: list[dict]) -> str:
    if not sources:
        return answer
    lines = [f"- {item['title']}: {item['url']}" for item in sources]
    return answer.rstrip() + "\n\nKaynaklar:\n" + "\n".join(lines)


def clean_web_answer(answer: str) -> str:
    text = re.split(r"\n\s*(?:Kaynaklar|Sources)\s*:", answer, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s)\]>]+", "", text)
    text = re.sub(r"【[^】]+】|\[(?:\d+|cite[^\]]*)\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _source_instruction(intent: str, folded: str) -> str:
    if "obilet" in folded or (intent == "travel_search" and "otobus" in folded):
        return "Önce obilet.com; sonra resmi otobüs firması sayfası. Firma, saat, süre ve fiyatı doğrula."
    if any(term in folded for term in ("pegasus", "flypgs", "thy", "turkishairlines", "ajet", "ucak")):
        return "Önce flypgs.com ve turkishairlines.com; gerekiyorsa ajet.com. THY ile AJet'i birbirine eşitleme."
    if any(term in folded for term in ("tren", "yht", "tcdd")):
        return "Önce TCDD resmi kaynaklarını kullan."
    if any(term in folded for term in ("feribot", "budo", "ido", "deniz otobusu")):
        return "Önce İDO ve BUDO resmi kaynaklarını kullan."
    if any(term in folded for term in ("mediamarkt", "teknoloji")):
        return "Önce MediaMarkt, sonra Hepsiburada."
    if any(term in folded for term in ("hepsiburada", "trendyol", "alisveris")):
        return "Önce Hepsiburada, sonra Trendyol."
    return SOURCE_MATRIX.get(intent, "Resmi kaynakları ve güvenilir ikincil kaynakları kullan.")


async def answer_general_knowledge(message: str, session_id: str, prior_context: str = "") -> str:
    system = """Sen NOVA'sın. Bora'ya doğal, düzgün ve akıcı Türkiye Türkçesiyle cevap ver. Uydurma kelime, bozuk tamlama, anlamsız ifade veya çeviri kokan cümle kullanma. Kısa ama gerçekten işe yarayan cevap üret. Plan istenirse uygulanabilir, birbirinden farklı seçenekler hazırla; bütçe verilmişse bütçeyi anlamlı kullan ve toplamları açık yaz. Yerleşik genel bilgiyi kullanabilirsin. Kişisel bilgi, canlı fiyat, işletme saati, müsaitlik veya Google Workspace verisi uydurma. Emin değilsen açıkça bilmediğini söyle. Bora diye hitap et."""
    if prior_context:
        system += "\n\nKonuşma bağlamı:\n" + prior_context
    chat = (
        LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=session_id, system_message=system)
        .with_model("openai", "gpt-4o-mini")
        .with_params(temperature=0.2, max_tokens=900)
    )
    return await chat.send_message(UserMessage(text=message))


async def answer_live_web(
    message: str,
    session_id: str,
    intent: str = "web_search",
    workspace_context: str = "",
    prior_context: str = "",
) -> tuple[str, list[dict]]:
    now = datetime.now(gint.ISTANBUL_TZ)
    system = """You MUST use Google Search for every query and preserve verifiable source URLs. Sen NOVA'sın. Doğal, düzgün Türkiye Türkçesiyle kısa ve operasyonel yaz. Uydurma kelime veya bozuk cümle kullanma. Sahte mekan, fiyat, saat, sefer, menü, müsaitlik, koltuk veya film seansı üretme. Kullanıcı birden fazla seçenek/yöntem istediğinde hepsini tek seferde doğrulayamıyorsan bütün cevabı reddetme: doğrulayabildiğin seçenekleri kaynaklı biçimde ver, doğrulayamadığın her seçeneği ayrı ve açık biçimde 'doğrulanamadı' diye işaretle. Bir sağlayıcı özellikle istendiyse o sağlayıcıya ait gerçek kaynak bulunmadan onun adına fiyat/ürün/sefer yazma. Personal Memory karar filtresini sessiz uygula; kullanıcı istemedikçe profil listesi okuma. Satın alma veya rezervasyon yaptığını söyleme. Kaynak URL'lerini ana cevap metnine doldurma."""
    search_request = f"Araştırma zamanı: {now.isoformat()}. Konum: Bursa, Türkiye.\nSoru: {message}"
    folded = fold_turkish(message)
    search_request += "\nKaynak önceliği: " + _source_instruction(intent, folded)
    if intent == "cinema_search":
        search_request += f"\nBu zaman-kritik bir film seansı sorgusudur. Önce Google'da 'Cinetime ÖzdilekPark Nilüfer {now.date().isoformat()} film seansları' resmi programını ara; yarın ifadesi için ertesi günün gerçek seanslarını doğrula. Cinetime sonucu yoksa gerçek Bursa sinemalarına genişlet ve bunu açıkça söyle."
    if intent == "restaurant_search":
        search_request += f"\nBu zaman-kritik yerel işletme sorgusudur. Google Search ile Bursa'daki gerçek mekanların {now.date().isoformat()} güncel resmi sayfa, menü, telefon ve çalışma saati kaynaklarını ara. Saat tam doğrulanamıyorsa mekanı yine sun ama 'gitmeden önce teyit etmek iyi olur' de."
    preference_context = profile_context_for_web(message, intent)
    if preference_context:
        search_request += "\nKullanıcı tercihlerini cevapta listeleme; yalnız seçenek sıralamasında sessizce uygula: " + preference_context
    if any(term in folded for term in ("ulasim", "otobus", "ucak", "tren", "feribot", "arabayla", "rota")):
        search_request += "\nGüncel yol/geçiş ücretlerini, feribot veya toplu taşıma seferlerini, tahmini süreleri ve varsa fiyatları canlı kaynaklardan doğrula."
    if "istanbul" in folded and "arabayla" in folded:
        search_request += "\nÖzellikle O-5/Osmangazi Köprüsü, Eskihisar–Topçular araçlı feribotu ve Yalova–Pendik araçlı İDO seçeneklerinin güncel ücret, sefer ve toplam sürelerini karşılaştır."
    if prior_context:
        search_request += "\nÖnceki konuşma bağlamı: " + prior_context
    search_request += "\nCanlı Google Search kullanarak güncel kaynaklarla araştır, doğrula ve en mantıklı seçenekleri karşılaştır."

    answer, sources = "", []
    for attempt in range(2):
        request_text = search_request
        if attempt:
            if intent == "restaurant_search":
                request_text = (
                    "Zorunlu canlı Google Search yap. Bursa için şu gerçek adayların resmi web/menü/telefon/çalışma saati kaynaklarını ara: "
                    "Kadim Restaurant, Balkon Cafe & Restaurant, Fazıl Usta Çorbacısı, Pırpır Midye, Erbaylar Balıkçısı, Haflinger Çiftliği. "
                    "Soruya uygun doğrulayabildiğin 2-3 mekanı kaynak URL'leriyle sun; saat veya menü doğrulanamazsa yalnız o alanın teyit edilmesi gerektiğini söyle.\n" + search_request
                )
            else:
                request_text = (
                    "Zorunlu canlı Google Search yap. Genel bilgiden cevap verme. "
                    "Her güncel iddiayı doğrulanabilir kaynak URL'siyle destekle.\n" + search_request
                )
        chat = (
            LlmChat(
                api_key=os.environ["EMERGENT_LLM_KEY"],
                session_id=f"{session_id}:web:{attempt}",
                system_message=system,
            )
            .with_model("gemini", "gemini-2.5-flash")
            .with_tools([{"googleSearch": {}}])
            .with_params(temperature=0 if attempt else 0.15, max_tokens=3000)
        )
        try:
            response = await chat.send_message_with_tools(UserMessage(text=request_text))
            answer = (response.content or "").strip()
            sources = _annotation_sources(response.raw, answer)
            if answer and sources:
                if not _sources_satisfy_request(sources, folded) and attempt == 0:
                    search_request = (
                        "Kullanıcının açıkça istediği kaynakları atlama. "
                        "İstenen sağlayıcıların her biri için doğrulanabilir gerçek kaynak URL'si bul. "
                        "Bulamadığın sağlayıcı için veri uydurma; açıkça doğrulanamadığını söyle.\n"
                        + search_request
                    )
                    continue
                if _looks_truncated(answer, response.raw) and attempt == 0:
                    search_request = (
                        "Önceki yanıt çıktı sınırına takıldı. Aynı araştırmayı yeniden yap; "
                        "cevabı daha kısa tut ama kullanıcının istediği bütün seçenekleri, "
                        "fiyat/saat/süre gibi kritik alanları eksiksiz bitir. Yarım cümle bırakma.\n"
                        + search_request
                    )
                    continue
                break
        except Exception as exc:
            logger.error("Live web search attempt=%s failed type=%s", attempt + 1, type(exc).__name__)

    if not answer or not sources:
        logger.warning("Live web search returned no verifiable citations after retry")
        return WEB_FAILURE, []
    answer = clean_web_answer(answer)
    if not answer:
        return WEB_FAILURE, []
    if workspace_context and "eşleşen kayıt bulunamadı" not in workspace_context:
        answer = "Takvim/Workspace bağlamı:\n" + workspace_context + "\n\nCanlı araştırma:\n" + answer
    return answer, sources