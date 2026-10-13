"""Cost-aware general knowledge and grounded live web research services."""
from datetime import datetime, date
from pathlib import Path
from PIL import Image
import logging
import json
import os
import re

from openai import AsyncOpenAI
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, FileContentWithMimeType

import google_integration as gint
from date_resolver import fold_turkish
from personal_memory import profile_context_for_web


WEB_FAILURE = "Bu bilgiyi canlı kaynaktan doğrulayamadım, Bora."
logger = logging.getLogger("nova.intelligence")

TURKISH_MONTHS = {
    "ocak": 1,
    "subat": 2,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "ağustos": 8,
    "eylul": 9,
    "eylül": 9,
    "ekim": 10,
    "kasim": 11,
    "kasım": 11,
    "aralik": 12,
    "aralık": 12,
}


def _explicit_date_range_from_message(message: str):
    """Parse same-month Turkish ranges such as 13-19 Ekim 2026."""
    m = re.search(
        r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+"
        r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|"
        r"Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)"
        r"(?:\s+(\d{4}))?",
        message,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    start_day = int(m.group(1))
    end_day = int(m.group(2))
    month_name = m.group(3).lower()
    year = int(m.group(4)) if m.group(4) else datetime.now(gint.ISTANBUL_TZ).year
    month = TURKISH_MONTHS.get(month_name)

    if not month:
        return None

    try:
        return date(year, month, start_day), date(year, month, end_day)
    except ValueError:
        return None


def _answer_contains_out_of_range_event(answer: str, requested_range) -> bool:
    """Detect explicit event dates outside the requested date window."""
    if not answer or not requested_range:
        return False

    start_date, end_date = requested_range

    for match in re.finditer(
        r"\b(\d{1,2})\s+"
        r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|"
        r"Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)"
        r"\s+(\d{4})\b",
        answer,
        flags=re.IGNORECASE,
    ):
        day = int(match.group(1))
        month = TURKISH_MONTHS.get(match.group(2).lower())
        year = int(match.group(3))

        if not month:
            continue

        try:
            event_date = date(year, month, day)
        except ValueError:
            continue

        if event_date < start_date or event_date > end_date:
            return True

    return False

SOURCE_MATRIX = {
    "hotel_search": "Önce Hotels.com, sonra otelin resmi sitesi; yalnız gerçek otel kullan.",
    "restaurant_search": "Önce resmi mekan/menu bilgisi ve Yemeksepeti; gerçek çalışma saati ve menü doğrula.",
    "cinema_search": "Yalnızca önce Cinetime ÖzdilekPark Nilüfer resmi programı. Türkçe dublaj öncelikli. Kullanıcı istemeden diğer Bursa sinemalarına genişletme.",
    "event_search": "Önce Biletinial, sonra Biletix; ardından resmi organizatör veya mekan sayfası. Gerçek tarih, saat, mekan ve mümkünse fiyat zorunlu.",
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
    if not text:
        return False

    # "2." / "3." gibi yeni madde başlayıp içerik gelmeden biten cevap yarımdır.
    if re.search(r"(?:^|\n)\s*\d+\.\s*$", text):
        return True

    # Başlık/markdown işaretiyle yarım kalan cevapları da yakala.
    if re.search(r"(?:\*\*|:|-)\s*$", text) and len(text) > 500:
        return True

    if len(text) < 1200:
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
    if intent == "event_search":
        return "Önce Biletinial; sonra Biletix; ardından resmi organizatör veya mekan sayfası. Etkinlik adı, tarih, saat, mekan ve varsa fiyatı doğrula."
    return SOURCE_MATRIX.get(intent, "Resmi kaynakları ve güvenilir ikincil kaynakları kullan.")


async def answer_general_knowledge(message: str, session_id: str, prior_context: str = "") -> str:
    system = """Sen NOVA'sın. Bora'ya doğal, düzgün ve akıcı Türkiye Türkçesiyle cevap ver. Uydurma kelime, bozuk tamlama, anlamsız ifade veya çeviri kokan cümle kullanma. Kısa ama gerçekten işe yarayan cevap üret. Ham veri veya rapor dili kullanma; önce bilgiyi yorumla ve Bora ile karşılıklı konuşuyormuş gibi anlat. Gereksiz numaralandırma yapma. Uygun olduğunda "istersen buradan başlayabiliriz", "bunu önce netleştirsek iyi olur" gibi doğal geçişler kullan; ama yapay samimiyet ve gereksiz gevezelik yapma. Plan istenirse uygulanabilir, birbirinden farklı seçenekler hazırla; bütçe verilmişse bütçeyi anlamlı kullan ve toplamları açık yaz. Yerleşik genel bilgiyi kullanabilirsin. Kişisel bilgi, canlı fiyat, işletme saati, müsaitlik veya Google Workspace verisi uydurma. Kullanıcının eşi, ailesi veya yakınları için öneri verirken kayıtlı olmayan zevk, yemek, marka, beden, renk veya tercih icat etme. Bildiğin kişisel bağlamı kullan; bilmediğin ayrıntıyı varsayma. Cevabı doğal ve tekil Türkçe ile bitir; "değerlendirebilirsiniz" gibi resmi/çoğul kalıplar yerine "istersen..." gibi konuşma dili kullan. Emin değilsen açıkça bilmediğini söyle. Bora diye hitap et."""
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
    system = """You MUST use live web search for every query and preserve verifiable source URLs. Sen NOVA'sın. Doğal, düzgün Türkiye Türkçesiyle kısa ve operasyonel yaz. Uydurma kelime veya bozuk cümle kullanma. Ham arama sonucu veya rapor gibi konuşma; bulduğun veriyi yorumlayıp Bora ile sohbet eder gibi aktar. Gereksiz maddeleme yapma; karşılaştırma gerçekten faydalıysa liste veya tablo kullan. Uygun olduğunda doğal bir sonraki adım öner. Sahte mekan, fiyat, saat, sefer, menü, müsaitlik, koltuk veya film seansı üretme. Kullanıcı birden fazla seçenek/yöntem istediğinde hepsini tek seferde doğrulayamıyorsan bütün cevabı reddetme: doğrulayabildiğin seçenekleri kaynaklı biçimde ver, doğrulayamadığın her seçeneği ayrı ve açık biçimde 'doğrulanamadı' diye işaretle. Bir sağlayıcı özellikle istendiyse o sağlayıcıya ait gerçek kaynak bulunmadan onun adına fiyat/ürün/sefer yazma. Personal Memory karar filtresini sessiz uygula; kullanıcı istemedikçe profil listesi okuma. Satın alma veya rezervasyon yaptığını söyleme. Bir mekanın pahalı/ucuz/makul olduğunu güncel fiyat verisi olmadan söyleme; fiyat doğrulanamıyorsa bunu açıkça belirt. Kullanıcının istemediği restoran veya genel mekan önerileriyle etkinlik listesini doldurma. Kaynak URL'lerini ana cevap metnine doldurma."""
    search_request = f"Araştırma zamanı: {now.isoformat()}. Konum: Bursa, Türkiye.\nSoru: {message}"
    folded = fold_turkish(message)
    requested_date_range = _explicit_date_range_from_message(message)
    search_request += "\nKaynak önceliği: " + _source_instruction(intent, folded)
    if intent == "cinema_search":
        search_request += (
            f"\nBu zaman-kritik bir film seansı sorgusudur. "
            f"Yalnızca önce Cinetime ÖzdilekPark Bursa Nilüfer için {now.date().isoformat()} tarihli gerçek programı araştır. "
            "Kaynak önceliği katıdır: film adı, seans saati, Türkçe dublaj/altyazı, salon ve varsa 3D bilgisi için önce cinetime.com.tr resmi sayfasını kullan. "
            "boxofficeturkiye.com kaynağını sinema araştırmalarında ASLA kullanma; bu domain yasaktır. "
            "Resmi Cinetime kaynağında bulunan bilgiyi BiletLink, haber sitesi, şehir rehberi veya başka ikincil kaynakla değiştirme. "
            "Resmi Cinetime'da bulunmayan bir ayrıntıyı ikincil kaynaktan kullanırsan bunun ikincil kaynak olduğunu açıkça belirt. "
            "Türkçe dublajlı seansları önceliklendir. Kullanıcının zevklerine uyan filmleri önce sırala. "
            "Bora için korku ve 3D artıdır; Bora ve Tuğba için bilim kurgu, fantastik ve komedi ortak yüksek önceliklidir; Tuğba için aksiyon ve romantik komedi artıdır. "
            "Cinetime ÖzdilekPark'ta uygun seçenek bulunamazsa kullanıcı açıkça istemeden diğer Bursa sinemalarına genişletme. "
            "Bunun yerine burada uygun seçenek bulamadığını söyle ve diğer Bursa sinemalarına da bakıp bakmaman gerektiğini sor."
        )

    if intent == "event_search":
        search_request += (
            "\nBu bir ETKİNLİK araştırmasıdır. Restoran, kafe veya sıradan mekan önerisini etkinlik gibi sunma. "
            "Yalnız belirli tarih/saatte gerçekleşen konser, tiyatro, sahne gösterisi, dans gösterisi, festival, "
            "özel kültür-sanat etkinliği veya kullanıcının tercihlerine uyan benzer gerçek etkinlikleri araştır. "
            "Kullanıcı ayrıca akşam planı, yemek veya özel gün istemediyse restoran ekleme. "
            "Her öneride etkinlik adı, tarih, saat, mekan ve neden Bora/Tuğba'ya uygun olduğunu belirt. "
            "Kaynak doğrulama sırası katıdır: önce Biletinial, sonra Biletix, sonra resmi organizatör veya mekan sayfası. "
            "Bir etkinlik Biletinial'da bulunuyorsa tarih, saat, mekan ve fiyat için Biletinial bilgisini esas al; "
            "ikincil sitelerdeki farklı saat veya fiyatı kullanma. "
            "Biletinial'da yoksa Biletix'i esas al. İkisinde de yoksa resmi organizatör veya mekan sayfasını kullan. "
            "Biletinial veya Biletix'te en az bir etkinlik bulduysan 'bu platformlarda etkinlik bulunamadı' deme; "
            "yalnız kaç etkinliği bu platformlardan doğrulayabildiğini doğru şekilde belirt. "
            "Bursadanevar, Biletevo, NeYapsak, Yapılacaklar.com, haber ve şehir rehberi siteleri yalnız keşif kaynağıdır. "
            "Bir etkinliği bu sitelerden keşfettiysen tarih/saat/mekan bilgisini mümkünse resmi mekan veya organizatör sayfasından tekrar doğrula. "
            "Resmi doğrulama bulunamazsa bu etkinliği kesin bilgi gibi sunma ve gerekirse listeyi 5'ten az seçenekle tamamla. "
            "Fiyat/bilet bilgisi bu birincil kaynaklardan doğrulanabiliyorsa yaz; doğrulanamıyorsa açıkça 'fiyat doğrulanamadı' de. "
            "Kullanıcı 5 seçenek istediyse 5 gerçek ve doğrulanmış seçenek bulmaya çalış; yalnız daha azı doğrulanabiliyorsa "
            "sahte seçenek tamamlamak yerine kaç tanesini doğrulayabildiğini açıkça söyle. "
            "Özel gün, doğum günü veya romantik planı kullanıcı açıkça istemediyse kendiliğinden varsayma."
        )
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
    search_request += "\nCanlı web araması kullanarak güncel kaynaklarla araştır, doğrula ve en mantıklı seçenekleri karşılaştır."

    answer, sources = "", []

    # ANA MOTOR — OpenAI Responses API + web_search
    openai_client = AsyncOpenAI(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
    )

    for attempt in range(2):
        request_text = search_request

        if attempt:
            request_text = (
                "Önceki araştırma eksik veya yarım kaldı. "
                "Aynı araştırmayı yeniden yap; daha kısa yaz fakat kullanıcının istediği "
                "bütün seçenekleri tamamla. Doğrulanmamış bilgi üretme. "
                "Yarım madde veya yarım cümle bırakma.\n"
                + search_request
            )

        try:
            web_tool = {"type": "web_search"}

            if intent == "cinema_search":
                request_text = (
                    "Önce özellikle şu sorguyla resmi kaynağı ara: "
                    "site:cinetime.com.tr Cinetime ÖzdilekPark Bursa Nilüfer bugün film seansları Türkçe dublaj. "
                    "Film adı, seans saati, salon ve dil bilgisini mümkün olduğunca doğrudan cinetime.com.tr üzerinden doğrula. "
                    "Resmi Cinetime sayfasında bulamadığın bilgiyi üçüncü taraf bir siteden kesin bilgi gibi sunma.\n"
                    + request_text
                )

            if intent == "event_search":
                request_text = (
                    "Etkinlik araştırmasında kullanıcının mesajındaki şehir ve tarih aralığını aynen kullan. "
                    "Önce site:biletinial.com üzerinde, sonra site:biletix.com üzerinde aynı şehir ve tarih aralığıyla "
                    "konser, tiyatro ve sahne etkinliklerini araştır. "
                    "Kullanıcının istemediği farklı tarih aralığına geçme. "
                    "Önce bu iki kaynaktan gerçek sonuç bulmaya çalış. "
                    "Biletinial veya Biletix'te bulunmayan etkinliğin fiyatını ikincil kaynaktan uydurma.\n"
                    + request_text
                )

            response = await openai_client.responses.create(
                model="gpt-4.1-mini",
                instructions=(
                    system
                    + "\nVerilen Araştırma zamanı değerini mevcut tarih ve saat için tek otorite kabul et. "
                    "Web sayfalarındaki eski 'bugün', 'yarın', 'bu hafta' ifadelerini mevcut tarih sanma. "
                    "Kullanıcının verdiği tarih aralığının dışındaki etkinliği ASLA önerme. "
                    "Örneğin 13-19 Ekim istenmişse 12 Ekim veya 20 Ekim ve sonrası sonuçlarını listeye alma. "
                    "Etkinlik cevabında doğal ve düzgün Türkiye Türkçesi kullan. "
                    "Cevabın giriş bölümü ile kaynaklar birbiriyle çelişmesin. "
                    "Biletix veya Biletinial kaynağı kullandıysan bu platformlarda sonuç bulunamadığını söyleme. "
                    "Bozuk ek, anlamsız tamlama veya makine çevirisi gibi cümle üretme. "
                    "Kullanıcının tercihlerini neden uygun olduğu bölümünde kısa ve doğal biçimde açıkla."
                ),
                tools=[web_tool],
                tool_choice="required",
                input=request_text,
            )

            answer = (response.output_text or "").strip()
            sources = _annotation_sources(response, answer)

            if answer and sources:
                if intent == "cinema_search":
                    cinema_urls = " ".join(
                        str(item.get("url", "")).lower()
                        for item in sources
                    )

                    if "boxofficeturkiye.com" in cinema_urls:
                        if attempt == 0:
                            search_request = (
                                "boxofficeturkiye.com yasaklı kaynaktır. "
                                "Bu domaini tamamen dışla. "
                                "Resmi Cinetime kaynağını yeniden ara; gerekirse daha az film ver ama Box Office Türkiye kullanma.\n"
                                + search_request
                            )
                            continue
                        else:
                            logger.warning("Cinema answer used forbidden Box Office Türkiye source")
                            return WEB_FAILURE, []

                    has_official_cinetime = "cinetime.com.tr" in cinema_urls

                    if not has_official_cinetime:
                        if attempt == 0:
                            search_request = (
                                "İlk araştırmada resmi Cinetime kaynağı gelmedi. "
                                "Yeniden araştır ve önce site:cinetime.com.tr üzerinden "
                                "Cinetime ÖzdilekPark Bursa Nilüfer film/seans sayfalarını bul. "
                                "Box Office Türkiye, BiletLink, haber veya şehir rehberi kaynaklarını "
                                "resmi Cinetime yerine ana kaynak yapma.\n"
                                + search_request
                            )
                            continue
                        else:
                            logger.warning(
                                "Cinema answer has no official Cinetime source after retry"
                            )
                            return WEB_FAILURE, []

                if (
                    intent == "event_search"
                    and requested_date_range
                    and _answer_contains_out_of_range_event(answer, requested_date_range)
                ):
                    if attempt == 0:
                        start_date, end_date = requested_date_range
                        search_request = (
                            f"KRİTİK TARİH KURALI: Yalnızca {start_date.isoformat()} ile "
                            f"{end_date.isoformat()} arasındaki etkinlikleri listele. "
                            "Bu aralığın dışındaki tek bir etkinliği bile cevaba alma. "
                            "5 seçenek bulamazsan daha az seçenek ver; tarih aralığını doldurmak için dışarı çıkma. "
                            "Türkçeyi kısa, doğal ve düzgün yaz.\n"
                            + search_request
                        )
                        continue
                    else:
                        logger.warning(
                            "Event answer still contains out-of-range dates after retry"
                        )
                        return WEB_FAILURE, []

                if intent == "event_search":
                    event_urls = " ".join(
                        str(item.get("url", "")).lower()
                        for item in sources
                    )
                    has_primary_event_source = (
                        "biletinial.com" in event_urls
                        or "biletix.com" in event_urls
                    )

                    if not has_primary_event_source and attempt == 0:
                        search_request = (
                            "İlk araştırmada Biletinial veya Biletix kaynağı gelmedi. "
                            "Yeniden araştır ve önce Biletinial, sonra Biletix sonuçlarını bul. "
                            "Bu iki kaynaktan doğrulanamayan saat/fiyat bilgisini kesin bilgi gibi verme.\n"
                            + search_request
                        )
                        continue

                if not _sources_satisfy_request(sources, folded) and attempt == 0:
                    search_request = (
                        "Kullanıcının açıkça istediği kaynak önceliğine katı biçimde uy. "
                        "Etkinlik aramasında Biletinial bulunduysa saat, tarih, mekan ve fiyat için onu tek ana doğrulama kaynağı kabul et. "
                        "Biletinial yoksa Biletix; o da yoksa resmi organizatör veya mekan sayfasına geç. "
                        "İkincil sitelerdeki fiyat veya saat bilgisini birincil kaynak yerine kullanma.\n"
                        + search_request
                    )
                    continue

                if _looks_truncated(answer, response) and attempt == 0:
                    search_request = (
                        "Önceki cevap yarım kaldı. Daha kısa yaz ama bütün istenen maddeleri bitir. "
                        "Yarım başlık, yarım madde veya yarım cümle bırakma.\n"
                        + search_request
                    )
                    continue

                break

        except Exception as exc:
            logger.error(
                "OpenAI live web attempt=%s failed type=%s",
                attempt + 1,
                type(exc).__name__,
            )

    # YEDEK MOTOR — OpenAI başarısızsa mevcut Gemini + Google Search
    if not answer or not sources:
        logger.warning("OpenAI web search failed; Gemini fallback starting")
        answer, sources = "", []

        for attempt in range(2):
            request_text = search_request

            if attempt:
                request_text = (
                    "Zorunlu canlı Google Search yap. Genel bilgiden cevap verme. "
                    "Güncel iddiaları doğrulanabilir kaynaklarla destekle. "
                    "Cevabı kısa tut ama bütün istenen maddeleri tamamla.\n"
                    + search_request
                )

            chat = (
                LlmChat(
                    api_key=os.environ["EMERGENT_LLM_KEY"],
                    session_id=f"{session_id}:web:fallback:{attempt}",
                    system_message=system,
                )
                .with_model("gemini", "gemini-2.5-flash")
                .with_tools([{"googleSearch": {}}])
                .with_params(
                    temperature=0 if attempt else 0.15,
                    max_tokens=3000,
                )
            )

            try:
                response = await chat.send_message_with_tools(
                    UserMessage(text=request_text)
                )
                answer = (response.content or "").strip()
                sources = _annotation_sources(response.raw, answer)

                if answer and sources:
                    if _looks_truncated(answer, response.raw) and attempt == 0:
                        continue
                    break

            except Exception as exc:
                logger.error(
                    "Gemini fallback attempt=%s failed type=%s",
                    attempt + 1,
                    type(exc).__name__,
                )

    if not answer or not sources:
        logger.warning("Live web search returned no verifiable citations after retry")
        return WEB_FAILURE, []
    answer = clean_web_answer(answer)
    if not answer:
        return WEB_FAILURE, []
    if workspace_context and "eşleşen kayıt bulunamadı" not in workspace_context:
        answer = "Takvim/Workspace bağlamı:\n" + workspace_context + "\n\nCanlı araştırma:\n" + answer
    return answer, sources

async def analyze_attachment(
    file_path: str,
    mime_type: str,
    filename: str,
    instruction: str,
    session_id: str,
) -> str:
    """Analyze one user-supplied image or PDF without inventing missing fields."""
    system = """Sen NOVA'sın. Bora'nın yüklediği belgeyi dikkatle incele.
Belgede açıkça görünmeyen hiçbir tarihi, saati, firma adını, güzergahı, PNR'ı,
rezervasyon kodunu, terminali, havalimanını veya fiyatı uydurma.

Bilet/rezervasyon belgesiyse mümkün olan alanları doğal Türkçe ile çıkar:
- yolcu
- firma / havayolu / otobüs firması
- gidiş tarihi ve kalkış saati
- kalkış yeri
- varış yeri ve varsa varış saati
- dönüş tarihi ve saati
- PNR / rezervasyon kodu
- koltuk
- terminal / havalimanı
- önemli notlar

Kullanıcı takvime işleme talebinde bulunmuş olsa bile bu aşamada yalnızca
belgeden doğruladığın bilgileri çıkar. Eksik alanları 'belgede görünmüyor'
diye belirt. Kısa, temiz ve doğal Türkiye Türkçesi kullan."""

    chat = (
        LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=session_id,
            system_message=system,
        )
        .with_model("gemini", "gemini-2.5-flash")
        .with_params(temperature=0.0, max_tokens=1200)
    )

    prompt = instruction.strip() or "Bu belgeyi incele ve içindeki önemli bilgileri çıkar."

    if mime_type.startswith("image/"):
        import base64
        raw = Path(file_path).read_bytes()
        content = ImageContent(base64.b64encode(raw).decode("ascii"))
    elif mime_type == "application/pdf":
        content = FileContentWithMimeType("application/pdf", file_path)
    else:
        raise ValueError("Desteklenmeyen dosya türü")

    return await chat.send_message(
        UserMessage(text=prompt, file_contents=[content])
    )


async def analyze_attachments(
    files: list[tuple[str, str, str]],
    instruction: str,
    session_id: str,
) -> str:
    """Read each travel document separately as JSON, then merge deterministically."""
    import base64
    import json

    records = []

    system = """Sen NOVA'nın seyahat belgesi okuyucususun.

Sana TEK bir görsel veya PDF verilecek.
Sadece dosyada açıkça görülen bilgileri çıkar.
Hiçbir tarih, saat, firma, PNR, güzergah, koltuk, terminal/peron veya fiyat uydurma.

SADECE geçerli JSON döndür. Markdown veya açıklama yazma.

Şema:
{
  "records": [
    {
      "direction": "",
      "passenger": "",
      "company": "",
      "date": "",
      "departure_time": "",
      "departure": "",
      "arrival": "",
      "arrival_time": "",
      "pnr": "",
      "seat": "",
      "terminal": "",
      "notes": ""
    }
  ]
}

Kurallar:
- Görünmeyen alan boş string olsun.
- direction yalnız açıkça anlaşılıyorsa "Gidiş" veya "Dönüş" olsun.
- Bir dosyada birden fazla gerçek seyahat kaydı varsa ayrı nesne üret.
- Tarih ve saatleri dosyada gördüğün şekilde doğru aktar.
- JSON kısa ve eksiksiz olsun."""

    for index, (file_path, mime_type, filename) in enumerate(files):
        contents = []

        if mime_type.startswith("image/"):
            raw = Path(file_path).read_bytes()
            contents.append(
                ImageContent(base64.b64encode(raw).decode("ascii"))
            )
        elif mime_type == "application/pdf":
            contents.append(
                FileContentWithMimeType("application/pdf", file_path)
            )
        else:
            continue

        parsed = None

        for attempt in range(3):
            chat = (
                LlmChat(
                    api_key=os.environ["EMERGENT_LLM_KEY"],
                    session_id=f"{session_id}:file:{index}:attempt:{attempt}",
                    system_message=system,
                )
                .with_model("gemini", "gemini-2.5-flash")
                .with_params(temperature=0.0, max_tokens=900)
            )

            prompt = (
                "Bu seyahat belgesini dikkatle oku ve yalnız doğruladığın bilgileri JSON olarak çıkar."
            )
            if attempt:
                prompt += " Önceki çıktı geçerli JSON değildi; bu kez eksiksiz JSON üret."

            raw_answer = await chat.send_message(
                UserMessage(text=prompt, file_contents=contents)
            )

            text = str(raw_answer).strip()
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

            try:
                data = json.loads(text)
                candidate = data.get("records", [])
                if isinstance(candidate, list):
                    parsed = candidate
                    break
            except Exception:
                continue

        if not parsed:
            continue

        for item in parsed:
            if not isinstance(item, dict):
                continue

            clean = {
                "direction": str(item.get("direction") or "").strip(),
                "passenger": str(item.get("passenger") or "").strip(),
                "company": str(item.get("company") or "").strip(),
                "date": str(item.get("date") or "").strip(),
                "departure_time": str(item.get("departure_time") or "").strip(),
                "departure": str(item.get("departure") or "").strip(),
                "arrival": str(item.get("arrival") or "").strip(),
                "arrival_time": str(item.get("arrival_time") or "").strip(),
                "pnr": str(item.get("pnr") or "").strip(),
                "seat": str(item.get("seat") or "").strip(),
                "terminal": str(item.get("terminal") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
            }

            if any(clean.values()):
                records.append(clean)

    if not records:
        return (
            "Bora, bilet görsellerinden güvenilir bir seyahat kaydı çıkaramadım. "
            "Eksik bilgiyi tahmin ederek devam etmiyorum."
        )

    # Aynı seyahatin farklı ekran görüntülerinden gelen kayıtlarını birleştir.
    merged = []

    def same_trip(a, b):
        strong = 0
        for key in ("date", "departure_time", "company", "departure", "arrival", "pnr"):
            av = a.get(key, "").casefold()
            bv = b.get(key, "").casefold()
            if av and bv and av == bv:
                strong += 1
        return strong >= 2

    for record in records:
        target = next((item for item in merged if same_trip(item, record)), None)

        if target is None:
            merged.append(record.copy())
            continue

        for key, value in record.items():
            if value and not target.get(key):
                target[key] = value

    # Tarihe göre sıralamaya çalış.
    def sort_key(item):
        return (
            item.get("date", ""),
            item.get("departure_time", ""),
        )

    merged.sort(key=sort_key)

    # Direction boşsa iki kayıt varsa kronolojik olarak gidiş/dönüş ata.
    if len(merged) >= 2:
        if not merged[0].get("direction"):
            merged[0]["direction"] = "Gidiş"
        if not merged[1].get("direction"):
            merged[1]["direction"] = "Dönüş"

    def trip_sentence(item, direction):
        date_value = item.get("date", "")
        time_value = item.get("departure_time", "")
        company = item.get("company", "")
        departure = item.get("departure", "")
        arrival = item.get("arrival", "")
        arrival_time = item.get("arrival_time", "")
        seat = item.get("seat", "")
        pnr = item.get("pnr", "")
        terminal = item.get("terminal", "")
        notes = item.get("notes", "")

        parts = []

        if direction == "Gidiş":
            parts.append("Gidişin")
        elif direction == "Dönüş":
            parts.append("Dönüşün")
        else:
            parts.append("Seyahatin")

        if date_value:
            parts.append(date_value)

        if time_value:
            parts.append(f"saat {time_value}'de")

        if company:
            parts.append(f"{company} ile yolculuk yapıyorsun")

        sentence = " ".join(parts).strip() + "."

        route_parts = []

        if departure:
            route_parts.append(f"kalkış noktan {departure}")

        if arrival:
            route_parts.append(f"varış noktan {arrival}")

        if route_parts:
            sentence += " " + ", ".join(route_parts) + "."

        extras = []

        if arrival_time:
            extras.append(f"Varış saatin {arrival_time}")

        if seat:
            extras.append(f"koltuğun {seat} numara")

        if terminal:
            extras.append(f"terminal/peron bilgin {terminal}")

        if extras:
            sentence += " " + ", ".join(extras) + "."

        if pnr:
            sentence += f" PNR/rezervasyon kodun {pnr}."

        if notes:
            sentence += f" Ayrıca notta {notes}"

        return sentence

    going = None
    returning = None
    others = []

    for item in merged[:4]:
        direction = item.get("direction", "").casefold()

        if "gidi" in direction and going is None:
            going = item
        elif ("dön" in direction or "don" in direction) and returning is None:
            returning = item
        else:
            others.append(item)

    sentences = ["Bora, biletlerini okudum."]

    if going:
        sentences.append(trip_sentence(going, "Gidiş"))

    if returning:
        sentences.append(trip_sentence(returning, "Dönüş"))

    for item in others:
        sentences.append(trip_sentence(item, "Seyahat"))

    sentences.append(
        "İstersen şimdi doğruladığım gidiş ve dönüş bilgilerini takvimine işleyebilirim."
    )

    return " ".join(sentences)


async def extract_calendar_items_from_attachment(
    attachment_analysis: str,
    session_id: str,
) -> list[dict]:
    """Convert a verified attachment analysis into safe calendar items."""
    system = """Sen NOVA'nın belge-takvim dönüştürücüsün.

Sana yalnızca daha önce görseller/PDF'lerden çıkarılmış bir analiz verilecek.
SADECE bu metinde açıkça bulunan bilgileri kullan.

Asla tarih, saat, firma, güzergah, PNR, terminal veya yer uydurma.

Sadece takvime konulabilecek seyahat hareketlerini çıkar:
- gidiş
- dönüş

Her kayıt için date ve time zorunlu.
Bir kaydın tarihi veya saati yoksa o kaydı items listesine koyma.

SADECE geçerli JSON döndür. Markdown veya açıklama yazma.

Şema:
{
  "items": [
    {
      "title": "Gidiş — Firma — Kalkış → Varış",
      "date": "YYYY-MM-DD",
      "time": "HH:MM",
      "location": "kalkış noktası veya boş",
      "description": "Belgeden doğrulanan PNR, firma, güzergah, varış saati, koltuk ve diğer önemli bilgiler"
    }
  ]
}

En fazla 4 kayıt üret."""

    chat = (
        LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=session_id,
            system_message=system,
        )
        .with_model("gemini", "gemini-2.5-flash")
        .with_params(temperature=0.0, max_tokens=1000)
    )

    raw = await chat.send_message(
        UserMessage(text=attachment_analysis)
    )

    text = str(raw).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    data = json.loads(text)
    items = data.get("items", [])

    safe = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue

        date_value = str(item.get("date", "")).strip()
        time_value = str(item.get("time", "")).strip()

        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            continue
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
            continue

        safe.append({
            "title": str(item.get("title") or "Seyahat").strip(),
            "date": date_value,
            "time": time_value,
            "location": str(item.get("location") or "").strip(),
            "description": str(item.get("description") or "").strip(),
        })

    return safe
