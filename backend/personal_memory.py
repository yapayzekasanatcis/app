"""Deterministic personal memory and preferences for Bora Ünsal."""
from datetime import date, datetime
from typing import Optional

from date_resolver import fold_turkish


MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

BORA_PROFILE = {
    "name": "Bora Ünsal",
    "birth_date": date(1978, 5, 12),
    "city": "Bursa",
    "professions": ["Yapay Zeka Sanatçısı", "Prodüktör", "AI Klip Yönetmeni", "Tiyatral Nikah Sanatçısı"],
    "vehicle": "Fiat Egea",
}

FAMILY_BIRTHDAYS = {
    "tugba": {"label": "Tuğba", "date": date(1990, 11, 10), "show_year": True},
    "atakan": {"label": "Atakan", "date": date(2000, 1, 11), "show_year": False},
    "anne": {"label": "Annen", "date": date(2000, 7, 13), "show_year": False},
    "tolga": {"label": "Tolga", "date": date(2000, 7, 29), "show_year": False},
}

SPECIAL_DAYS = {
    "sevgililer": (2, 14, "Sevgililer Günü 14 Şubat"),
    "kadinlar": (3, 8, "Dünya Kadınlar Günü 8 Mart"),
    "evlilik": (1, 11, "Evlilik yıldönümünüz 11 Ocak"),
}

SOUPS = ["kaşarlı domates", "mercimek", "ezogelin"]
FAVORITE_FOODS = [
    "köfte", "etli yemekler", "fast food", "etli/sucuklu/kıymalı pizza",
    "tantuni", "kokoreç", "midye dolma", "midye tava",
]


def _next_occurrence(value: date, today: date) -> date:
    candidate = date(today.year, value.month, value.day)
    return candidate if candidate >= today else date(today.year + 1, value.month, value.day)


def _birthday_subject(folded: str) -> Optional[dict]:
    if "tugba" in folded or "tuba" in folded or "esim" in folded:
        return FAMILY_BIRTHDAYS["tugba"]
    if "atakan" in folded or "oglum" in folded:
        return FAMILY_BIRTHDAYS["atakan"]
    if "annem" in folded or "annemin" in folded:
        return FAMILY_BIRTHDAYS["anne"]
    if "tolga" in folded or "kardesim" in folded:
        return FAMILY_BIRTHDAYS["tolga"]
    if "benim" in folded or "dogum tarihim" in folded or "bora" in folded:
        return {"label": "Senin", "date": BORA_PROFILE["birth_date"], "show_year": True}
    return None


def _birthday_reply(subject: dict, folded: str, today: date) -> str:
    value = subject["date"]
    if "kac gun" in folded or "ne kadar kaldi" in folded:
        days = (_next_occurrence(value, today) - today).days
        return f"{subject['label']} doğum gününe {days} gün kaldı, Bora."
    rendered = f"{value.day} {MONTHS[value.month - 1]}"
    if subject["show_year"]:
        rendered += f" {value.year}"
    if subject["label"] == "Senin":
        return f"Doğum tarihin {rendered}, Bora."
    return f"{subject['label']} doğum günü {rendered}, Bora."


def _upcoming_family_birthday(today: date) -> str:
    people = [
        {"label": "Tuğba'nın", "date": FAMILY_BIRTHDAYS["tugba"]["date"]},
        {"label": "Atakan'ın", "date": FAMILY_BIRTHDAYS["atakan"]["date"]},
        {"label": "annenin", "date": FAMILY_BIRTHDAYS["anne"]["date"]},
        {"label": "Tolga'nın", "date": FAMILY_BIRTHDAYS["tolga"]["date"]},
    ]
    next_person = min(people, key=lambda item: _next_occurrence(item["date"], today))
    occurrence = _next_occurrence(next_person["date"], today)
    days = (occurrence - today).days
    return f"Yaklaşan aile doğum günü {next_person['label']} doğum günü: {occurrence.day} {MONTHS[occurrence.month - 1]}. {days} gün kaldı, Bora."


def _looks_personal_unknown(folded: str) -> bool:
    subjects = ("tugba", "tuba", "atakan", "tolga", "annem", "annemin", "esim", "oglum", "kardesim")
    questions = (" ne", "nedir", "nasil", "kac", "hangi", "numara", "beden", "boy", "kilo", "seviyor")
    return any(subject in folded for subject in subjects) and any(word in f" {folded}" for word in questions)


def personal_memory_reply(message: str, now: datetime) -> Optional[dict]:
    folded = fold_turkish(message)
    today = now.date()

    if "yaklasan" in folded and "aile" in folded and "dogum gun" in folded:
        return {"intent": "personal_memory", "reply": _upcoming_family_birthday(today)}

    subject = _birthday_subject(folded)
    if subject and ("dogum" in folded or "kac gun" in folded or "ne kadar kaldi" in folded):
        return {"intent": "personal_memory", "reply": _birthday_reply(subject, folded, today)}

    if "corba" in folded and any(word in folded for word in ("sev", "hangi", "tercih")):
        return {"intent": "personal_memory", "reply": "Sevdiğin çorbalar kaşarlı domates, mercimek ve ezogelin, Bora."}

    if "sebze" in folded and any(word in folded for word in ("oner", "yemek", "yiyeyim")):
        return {
            "intent": "personal_memory",
            "reply": "Sebze yemeği yemediğini bildiğim için önermiyorum, Bora. Köfte, etli yemek, tantuni veya etli bir pizza düşünebiliriz.",
        }

    if "mayonez" in folded:
        return {"intent": "personal_memory", "reply": "Mayonez istemiyorsun, Bora."}

    if "sevdigim yemek" in folded or "hangi yemekleri" in folded or "ne yemeyi severim" in folded:
        return {"intent": "personal_memory", "reply": "Sevdiğin başlıca yiyecekler: " + ", ".join(FAVORITE_FOODS) + ", Bora."}

    if "istanbul" in folded and any(phrase in folded for phrase in ("genelde nasil", "nasil gitmek isterim", "ulasim tercihim", "seyahat tercihim")):
        return {
            "intent": "personal_memory",
            "reply": "Bursa–İstanbul gibi yakın mesafelerde önceliğin özel araç, Bora. Trafik ve programa göre köprü, Eskihisar–Topçular veya Yalova–Pendik seçeneklerini karşılaştırmayı; araçsızsan BUDO ya da İDO'yu değerlendirmeyi tercih ediyorsun.",
        }

    if "arabam" in folded or "aracim" in folded:
        return {"intent": "personal_memory", "reply": "Aracın Fiat Egea, Bora."}

    if "ben kimim" in folded or "meslegim" in folded:
        professions = ", ".join(BORA_PROFILE["professions"])
        return {"intent": "personal_memory", "reply": f"Sen Bora Ünsal'sın; {professions} olarak çalışıyorsun ve Bursa'da yaşıyorsun."}

    for key, (month, day, label) in SPECIAL_DAYS.items():
        if key in folded or (key == "kadinlar" and "8 mart" in folded):
            return {"intent": "personal_memory", "reply": f"{label}, Bora."}

    if _looks_personal_unknown(folded):
        return {
            "intent": "unknown_fallback",
            "reply": "Bu bilgi bende kayıtlı değil, Bora. İstersen bunu kişisel profiline ekleyebiliriz.",
        }
    return None


def profile_context_for_web(message: str = "", intent: str = "") -> str:
    folded = fold_turkish(message)
    if intent in {"web_search", "shopping_search"}:
        return ""
    if intent == "hotel_search" or "otel" in folded:
        companion = "Tuğba ile seyahatte geniş yatak; sigara içilebilen oda tercih edilebilir." if "tugba" in folded else "Yalnız seyahatte tek kişilik, geniş yataklı, sigara içilmeyen oda tercih edilir."
        purpose = "Tatil planında spa, termal ve havuz avantajdır." if any(term in folded for term in ("tatil", "termal", "gezi")) else "İş seyahatinde spa/termal/havuz öncelikli değildir."
        return f"{companion} {purpose} Karar sırası fiyat, manzara, merkeze yakınlık. Tatilde yaklaşık 10.000 TL başlangıç bütçesi referanstır; sabit üst limit değildir. Hotels.com ve resmi otel verisini kullan."
    if intent == "cinema_search" or "sinema" in folded or "film" in folded:
        return "Bursa'da önce Cinetime ÖzdilekPark Nilüfer'i kontrol et. Bora korku, komedi, bilim kurgu ve animasyon; Tuğba aksiyon, bilim kurgu ve animasyon sever. Ortak seçimde bilim kurgu ve animasyon önceliklidir. Küçük salonda orta sıra; VIP/Gold Class fiyat farkı makulse değerlendir."
    if intent == "restaurant_search" or any(term in folded for term in ("restoran", "yemek yiy", "corbaci", "corba")):
        return "Bora sebze ve sulu yemek yemez; köfte, et, fast food, etli pizza, tantuni, kokoreç, midye ve kaşarlı domates/mercimek/ezogelin çorbası uygundur; mayonez istemez. Tuğba ev yemeği sever ama ortak planda Bora'ya uyum sağlar. Manzara avantajdır; kişi başı yaklaşık 1000 TL başlangıç referansıdır. Balkon Cafe, Kadim Restaurant, Fazıl Usta Çorbacısı, Pırpır Midye, Erbaylar Balıkçısı ve Haflinger Çiftliği yalnız bağlama uygunsa tercih sinyalidir."
    if intent == "event_search":
        return "Tuğba ile planda canlı müzik öncelikli; sonra club. Tiyatroda komedi, konserde güçlü sahne şovu tercih edilir. Yalnız gerçek etkinlik ve resmi/kanıtlanabilir tarih-saat kullan."
    if intent == "leisure_search":
        return "Tuğba ile çok yorucu olmayan gerçek plan yap. Kahve, uygun yemek ve gerçek etkinliği dengeli sırala. Kahvaltıda Balkon Cafe veya Haflinger Çiftliği bağlama uygunsa avantajdır."
    travel_terms = ("ulasim", "otobus", "ucak", "tren", "yht", "feribot", "arabayla", "rota", "otel", "seyahat")
    if intent == "travel_search" or any(term in folded for term in travel_terms) or "gezi" in folded:
        return """Başlangıç Bursa. Yakın mesafede özel araç; uygun hat varsa TCDD/YHT; deniz geçişinde feribot/deniz otobüsü değerlendir. TAG, sonra otobüs/metro, gerekirse taksi. Otobüste Pamukkale, Kamil Koç, Lüks Karadeniz, Varan ve Özkaymak tercih sinyalidir; mümkünse ön, yoksa cam kenarı ama koltuğu satın alma ekranında doğrula. Uçakta Pegasus sonra THY; SAW, sonra IST, avantajlı direkt uçuş varsa Yenişehir. AJet'i THY diye sunma. Uçakta cam kenarı, acil çıkış değil; kısa seyahatte kabin bagajı. YHT Business fiyat farkı makulse, değilse cam kenarı. Özel araçta ücretli yolu yalnız belirgin avantaj varsa öner; İstanbul için önce Eskihisar–Topçular, sonra köprü/Yalova–Pendik/BUDO/İDO seçeneklerini güncel veriyle karşılaştır."""
    return """Bora sebze yemeği yemez. Köfte, etli yemekler, fast food, etli/sucuklu/kıymalı pizza, tantuni, kokoreç, midye dolma ve midye tava sever. Sevdiği çorbalar kaşarlı domates, mercimek ve ezogelindir. Mayonez istemez."""


def personal_context_for_keys(keys: list[str]) -> str:
    parts = []
    if "tugba" in keys:
        parts.append("Tuğba Bora'nın eşidir; doğum tarihi 10 Kasım 1990. Hediye/sürprizde çiçek, tatlı, yemek ve duruma göre tatil uygundur.")
    if "atakan" in keys:
        parts.append("Atakan Bora'nın oğludur; doğum günü 11 Ocak.")
    if "food_preferences" in keys:
        parts.append(profile_context_for_web("restoran", "restaurant_search"))
    if "travel_preferences" in keys:
        parts.append(profile_context_for_web("seyahat", "travel_search"))
    return "\n".join(parts)


def required_memory_fact_prefix(keys: list[str]) -> str:
    facts = []
    if "tugba" in keys:
        facts.append("Tuğba'nın doğum günü 10 Kasım.")
    if "atakan" in keys:
        facts.append("Atakan'ın doğum günü 11 Ocak.")
    return " ".join(facts)