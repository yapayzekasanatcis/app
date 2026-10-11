"""Central semantic routing contract for NOVA."""
from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Optional

from date_resolver import ResolvedTemporal, fold_turkish, resolve_temporal


@dataclass
class RouteDecision:
    intent: str
    connector: str = "none"
    provider: Optional[str] = None
    target_date: Optional[date] = None
    range_start: Optional[date] = None
    range_end: Optional[date] = None
    target_time: Optional[str] = None
    target_entity: Optional[str] = None
    target_tab: Optional[str] = None
    target_document: Optional[str] = None
    action: Optional[str] = None
    requested_items: list[str] = field(default_factory=list)
    memory_context_keys: list[str] = field(default_factory=list)
    forbidden_routes: list[str] = field(default_factory=list)
    requires_web: bool = False


def _requested_items(folded: str) -> list[str]:
    candidates = {
        "özel araç": ("ozel arac", "arabayla", "aracla"),
        "otobüs": ("otobus", "obilet"),
        "uçak": ("ucak", "pegasus", "thy", "ajet"),
        "tren/YHT": ("tren", "yht", "tcdd"),
        "deniz yolu": ("deniz", "feribot", "budo", "ido"),
        "otel": ("otel", "konaklama"),
        "yemek": ("yemek", "restoran"),
        "etkinlik": ("etkinlik", "konser", "tiyatro"),
    }
    return [label for label, terms in candidates.items() if any(term in folded for term in terms)]


def _memory_keys(folded: str) -> list[str]:
    keys = []
    if "tugba" in folded or "esim" in folded:
        keys.append("tugba")
    if "atakan" in folded or "oglum" in folded:
        keys.append("atakan")
    if any(term in folded for term in ("yemek", "restoran", "corba")):
        keys.append("food_preferences")
    if any(term in folded for term in ("otel", "seyahat", "gezi", "ulasim", "ucak", "otobus")):
        keys.append("travel_preferences")
    return keys


def _provider(folded: str) -> tuple[Optional[str], Optional[str]]:
    providers = [
        ("gemini", ("gemini",)), ("google_search", ("google'da", "googleda", "web'de", "webde")),
        ("obilet", ("obilet",)), ("hotels", ("hotels.com", "hotels")),
        ("hepsiburada", ("hepsiburada",)), ("mediamarkt", ("mediamarkt",)),
        ("trendyol", ("trendyol",)), ("yemeksepeti", ("yemeksepeti",)),
        ("pegasus", ("pegasus", "flypgs")), ("thy", ("turkishairlines", "thy")),
        ("ajet", ("ajet",)), ("tcdd", ("tcdd", "yht")),
        ("ido", ("ido",)), ("budo", ("budo",)),
    ]
    matched = [name for name, terms in providers if any(term in folded for term in terms)]
    return (matched[0], ",".join(matched)) if matched else (None, None)


def _document_title(message: str) -> Optional[str]:
    quoted = re.search(r"[\"“](.+?)[\"”]", message)
    if quoted:
        return quoted.group(1).strip()
    folded = fold_turkish(message)
    if "cekirdek kurallar" in folded:
        return "NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler"
    return None


def route_message(message: str, now: datetime) -> RouteDecision:
    folded = fold_turkish(message)
    temporal: ResolvedTemporal = resolve_temporal(message, now)
    base = dict(
        target_date=temporal.target_date,
        range_start=temporal.range_start,
        range_end=temporal.range_end,
        target_time=temporal.target_time,
        requested_items=_requested_items(folded),
        memory_context_keys=_memory_keys(folded),
    )

    if any(term in folded for term in ("seni test ediyorum", "seni deniyorum", "robotik oldu", "yanlis anladin", "davranisi sevmedim", "yeni versiyonda duzelt")):
        return RouteDecision("meta", forbidden_routes=["calendar", "workspace", "web"], **base)

    destructive = bool(re.search(r"\b(?:sil|kaldir)\b", folded))
    calendar_create_terms = (
        "takvime ekle", "takvimime ekle", "etkinligi ekle", "etkinlik ekle",
        "takvime kaydet", "takvimime kaydet", "takvime koy",
        "randevu ekle", "randevu olustur", "randevu oluştur",
        "gorusme ekle", "görüşme ekle",
        "eklenmesi", "ekleyelim", "ekler misin", "ekleyebilir misin",
    )
    if any(term in folded for term in calendar_create_terms):
        return RouteDecision("calendar_action", "calendar", action="create", **base)
    calendar_update_terms = (
        "bunu ertele", "bunu tası", "bunu tasi",
        "etkinligi guncelle", "etkinligi al",
        "gorusmeyi tasi", "görüşmeyi taşı",
        "randevuyu tasi", "randevuyu taşı",
        "saatine al", "saate al",
    )
    if any(term in folded for term in calendar_update_terms):
        return RouteDecision("calendar_action", "calendar", action="update", **base)

    calendar_delete_target = any(
        term in folded for term in (
            "etkinlik", "gorusme", "görüşme", "randevu",
            "takvim", "nikah", "nikâh"
        )
    )
    if destructive and calendar_delete_target:
        return RouteDecision("calendar_action", "calendar", action="delete", **base)
    if any(term in folded for term in ("gorev olarak ekle", "gorev ekle", "yapilacaklara ekle")):
        return RouteDecision("task_action", "sheets", target_tab="İşler", action="create", **base)
    if any(term in folded for term in ("tamamla", "tamamlandi", "tamamlandı")) and any(term in folded for term in ("gorev", "bilet", "is", "mekan")):
        return RouteDecision("task_action", "sheets", target_tab="İşler", action="complete", **base)
    if any(term in folded for term in ("kapat", "kapali yap", "kapalı yap")) and any(term in folded for term in ("gorev", "is", "bilet", "mekan")):
        return RouteDecision("task_action", "sheets", target_tab="İşler", action="close", **base)
    if any(term in folded for term in ("tekrar ac", "yeniden ac", "gorevi ac")):
        return RouteDecision("task_action", "sheets", target_tab="İşler", action="reopen", **base)
    if destructive and any(term in folded for term in ("gorev", "is", "bilet", "mekan")):
        return RouteDecision("task_action", "sheets", target_tab="İşler", action="delete", **base)
    if any(term in folded for term in ("gorevi hakkinda", "gorev hakkinda", "workspace'te kayitli bilgileri", "workspace te kayitli bilgileri")):
        return RouteDecision("sheets_read", "sheets", target_tab="İşler", **base)

    if ("belge" in folded or "dokuman" in folded or "docs" in folded) and "drive" in folded:
        return RouteDecision("docs_read", "docs", target_document=_document_title(message), **base)
    if "docs" in folded or "dokuman" in folded or "belge" in folded:
        return RouteDecision("docs_read", "docs", target_document=_document_title(message), **base)
    if "drive" in folded:
        return RouteDecision("drive_read", "drive", **base)
    if "gmail" in folded or re.search(r"\bmail", folded):
        return RouteDecision("gmail_read", "gmail", **base)
    target_tab = next((tab for tab in ("Projeler", "İşler", "Rutinler") if fold_turkish(tab) in folded), None)

    workspace_request = "workspace" in folded and any(
        term in folded for term in (
            "kontrol et", "durumu", "durumunu", "gorev", "gorevin",
            "kayitli", "bilgileri", "is merkezi"
        )
    )
    if workspace_request:
        return RouteDecision("sheets_read", "sheets", target_tab="İşler", **base)

    if "nova is merkezi" in folded or target_tab:
        return RouteDecision("sheets_read", "sheets", target_tab=target_tab, **base)

    provider, provider_group = _provider(folded)
    explicit_research = any(term in folded for term in ("arastir", "internetten", "webde", "web'de", "guncel bilgi", "resmi sitesini", "sosyal medya"))
    if provider or explicit_research:
        provider_intent = "web_search"
        if provider in {"obilet", "pegasus", "thy", "ajet", "tcdd", "ido", "budo"}:
            provider_intent = "travel_search"
        elif provider == "hotels":
            provider_intent = "hotel_search"
        elif provider in {"hepsiburada", "mediamarkt", "trendyol"}:
            provider_intent = "shopping_search"
        elif provider == "yemeksepeti":
            provider_intent = "restaurant_search"
        return RouteDecision(provider_intent, "web", provider=provider_group or provider, requires_web=True, **base)

    planning = any(term in folded for term in (
        "plan hazirla", "plani hazirla", "planla", "alternatif hazirla",
        "gunubirlik gezi", "gunluk gezi"
    ))
    if planning and not any(term in folded for term in ("fiyat", "ucret", "bilet", "sefer", "guncel", "arastir", "internetten")):
        return RouteDecision("planning", "general_llm", **base)

    if any(term in folded for term in ("tiyatral nikah is", "nikah islerim", "yaklasan nikah", "is listemi", "gorevlerim", "islerim", "projelerim")):
        return RouteDecision("personal_work", "workspace", **base)

    external_map = [
        ("hotel_search", ("otel", "konaklama")),
        ("cinema_search", ("sinema", "film seans")),
        ("restaurant_search", ("restoran", "yemek yiy", "corbaci", "corba bul")),
        ("shopping_search", ("laptop", "urun bul", "alisveris")),
        ("event_search", ("konser", "tiyatro", "etkinlik", "canli muzik")),
        ("travel_search", ("seyahat", "gezi", "ulasim", "otobus", "ucak", "tren", "feribot", "arabayla")),
        ("leisure_search", ("saatlik plan", "sehir plani")),
    ]
    for intent, terms in external_map:
        if any(term in folded for term in terms):
            return RouteDecision(intent, "web", requires_web=True, **base)

    if any(term in folded for term in ("musait miyim", "bos muyum", "plan koyabilir miyim", "takvimimde bir sey var mi", "programim var mi")):
        return RouteDecision("availability", "calendar", **base)
    if any(term in folded for term in (
        "bugunku 3 onceligim", "bugun 3 onceligim", "bugunku onceliklerim",
        "bugun onceliklerim", "bugun neye odaklanmaliyim"
    )):
        return RouteDecision("weekly_priorities", "workspace", **base)

    if any(term in folded for term in ("brifing", "briefing", "ne yapmaliyim", "kacirma risk", "onemli is")):
        if "kacirma risk" in folded or "onumuzdeki birkac gun" in folded:
            from datetime import timedelta
            base["range_start"] = now.date()
            base["range_end"] = now.date() + timedelta(days=4)
        return RouteDecision("briefing", "workspace", **base)
    if any(term in folded for term in ("bugun programim", "bugunku programim", "bugun ne var")):
        return RouteDecision("today_schedule", "calendar", **base)
    if any(term in folded for term in ("bekleyen is", "bekleyen gorev", "yapilacak is")):
        return RouteDecision("pending_tasks", "workspace", **base)
    if "komagene" in folded and any(term in folded for term in ("rutin", "bu hafta", "ne yap")):
        return RouteDecision("weekly_routines", "workspace", **base)
    if any(term in folded for term in ("takvimimde", "programim", "ne isim var", "nikah saat kac", "etkinligim")) or temporal.target_date:
        return RouteDecision("calendar_date_query", "calendar", **base)

    direct_memory = any(term in folded for term in (
        "dogum gun", "dogum gunum", "hangi corbalari severim", "arabam ne",
        "meslegim ne", "mesleklerim neler", "ben kimim", "hakkimda ne biliyorsun"
    ))
    if direct_memory:
        return RouteDecision("personal_memory", "memory", **base)
    return RouteDecision("general", "general_llm", **base)