"""Natural, complete and freshness-aware NOVA responses."""
from datetime import date
import re

from date_resolver import fold_turkish


def classify_calendar_event(event: dict) -> str:
    folded = fold_turkish(" ".join(str(event.get(key, "")) for key in ("title", "description", "calendar")))
    if any(term in folded for term in ("komagene", "sevkiyat", "siparis gunu", "stok kontrol", "lavas")):
        return "non_blocking_routine"
    if "T" not in str(event.get("start", "")):
        return "flexible_task"
    blocking_terms = (
        "tiyatral", "nikah", "doktor", "toplanti", "meeting", "ucus", "otobus",
        "rezervasyon", "konser", "randevu", "musteri", "appointment",
    )
    return "blocking" if any(term in folded for term in blocking_terms) else "blocking"


def _time(value: str) -> str:
    return value[11:16] if value and "T" in value else ""


def _short_location(value: str) -> str:
    if not value:
        return "konumu belirtilmemiş"
    return value.split(",")[0].strip()


def compose_calendar_answer(target: date, events: list[dict], calendar_ok: bool, question: str = "") -> str:
    label = f"{target.day} {['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'][target.month - 1]}"
    if not calendar_ok:
        return f"Bora, şu anda Calendar bağlantısından {label} programını alamıyorum."
    if not events:
        if "nikah" in fold_turkish(question):
            return f"Bora, {label} için kayıtlı bir Tiyatral Nikâh göremiyorum. Eğer gerçekten o tarihte bir işin varsa henüz takvime eklenmemiş olabilir. Şehir/konum ve saat bilgisini paylaşırsan kaydı hazırlayabiliriz."
        return f"Bora, {label} için seçili takvimlerinde kayıtlı etkinlik göremiyorum."
    if len(events) == 1:
        event = events[0]
        title = event.get("title", "etkinlik")
        location = _short_location(event.get("location", ""))
        start = _time(event.get("start", ""))
        description = event.get("description", "") or ""
        ceremony = re.search(r"(?:nik[aâ]h|baslangic|başlangıç)(?:\s+saati)?\s*[:：]?\s*(\d{1,2}:\d{2})", description, re.IGNORECASE)
        if "tiyatral" in fold_turkish(title) or "nikah" in fold_turkish(title):
            result = f"Bora, {label}’de {location}’de bir Tiyatral Nikâh’ın var."
            if start:
                result += f" {start}’da orada hazır olman gerekiyor"
            if ceremony:
                result += f"; nikâh {ceremony.group(1)}’de başlayacak"
            return result.rstrip(";") + "."
        return f"Bora, {label}’de {location}’de {title} var" + (f"; başlangıç {start}." if start else ".")
    rendered = []
    for event in events[:5]:
        start = _time(event.get("start", "")) or "tüm gün"
        rendered.append(f"{start} {event.get('title', 'Etkinlik')}")
    return f"Bora, {label} programında " + "; ".join(rendered) + "."


def compose_availability(target: date, target_time: str | None, events: list[dict], calendar_ok: bool) -> str:
    if not calendar_ok:
        return "Bora, şu anda Calendar bağlantısından müsaitlik sonucu alamıyorum."
    blocking = [event for event in events if classify_calendar_event(event) == "blocking"]
    if target_time:
        conflicts = [
            event for event in blocking
            if _time(event.get("start", "")) <= target_time < (_time(event.get("end", "")) or "23:59")
        ]
    else:
        conflicts = blocking
    if not conflicts:
        return f"Bora, {target.strftime('%d.%m.%Y')}" + (f" saat {target_time} civarında" if target_time else "") + " blocking bir etkinlik görünmüyor; müsait görünüyorsun. Komagene rutinlerini meşguliyet saymadım."
    event = conflicts[0]
    return f"Bora, o saat için {event.get('title', 'bir etkinlik')} kaydın var; müsait görünmüyorsun."


def apply_freshness_guard(answer: str, target_year: int, current_sensitive: bool) -> str:
    if not current_sensitive:
        return answer
    lines = answer.splitlines()
    kept, removed_old_price = [], False
    for line in lines:
        years = [int(value) for value in re.findall(r"\b(20\d{2})\b", line)]
        has_price = bool(re.search(r"(?:₺|\bTL\b|\blira\b)", line, re.IGNORECASE))
        if has_price and years and max(years) < target_year:
            removed_old_price = True
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    if removed_old_price:
        cleaned += "\n\nEski fiyatları güncel toplama katmadım; güncel ücretin resmi kaynaktan son kez doğrulanması gerekir."
    return cleaned


def ensure_requested_items(answer: str, requested_items: list[str]) -> str:
    folded = fold_turkish(answer)
    missing = [item for item in requested_items if not any(token in folded for token in fold_turkish(item).split("/"))]
    if not missing:
        return answer
    return answer.rstrip() + "\n\nDoğrulanmış sonuç bulamadığım seçenekler: " + ", ".join(missing) + "."


def ensure_complete_response(answer: str) -> str:
    text = answer.strip()
    if not text or text.endswith((".", "!", "?", ":", ")")):
        return text
    last = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    if last >= int(len(text) * 0.7):
        return text[:last + 1]
    return text + "."


def meta_reply(message: str) -> str:
    folded = fold_turkish(message)
    if "robotik" in folded or "yanlis" in folded or "sevmedim" in folded:
        return "Haklısın Bora; geri bildirimi aldım. Cevabı daha doğal, kısa ve doğrudan kuracağım."
    return "Tamam Bora, test modunda neyi kontrol etmek istediğini söyle; ilgili akışı birlikte doğrulayalım."