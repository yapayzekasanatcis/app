"""Resolve Turkish calendar expressions against Istanbul local time."""
import re
import unicodedata
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Optional

from dateparser.search import search_dates


MONTHS = {
    "ocak": 1,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "eylul": 9,
    "ekim": 10,
    "kasim": 11,
    "aralik": 12,
}
WEEKDAYS = {
    "pazartesi": 0,
    "sali": 1,
    "carsamba": 2,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}


@dataclass(frozen=True)
class ResolvedTemporal:
    target_date: Optional[date] = None
    range_start: Optional[date] = None
    range_end: Optional[date] = None
    target_time: Optional[str] = None
    phrase: Optional[str] = None


def fold_turkish(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("ı", "i").replace("İ", "I"))
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def resolve_requested_date(message: str, reference: datetime) -> Optional[date]:
    """Resolve explicit and relative Turkish date phrases; return None if absent."""
    text = fold_turkish(message)

    explicit = re.search(
        r"\b(\d{1,2})\s+(ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)(?:\s+(\d{4}))?\b",
        text,
    )
    if explicit:
        day = int(explicit.group(1))
        month = MONTHS[explicit.group(2)]
        year = int(explicit.group(3)) if explicit.group(3) else reference.year
        try:
            resolved = date(year, month, day)
        except ValueError:
            return None
        if not explicit.group(3) and resolved < reference.date():
            resolved = date(year + 1, month, day)
        return resolved

    if re.search(r"\bbugun\b", text):
        return reference.date()
    if re.search(r"\byarin\b", text):
        return reference.date() + timedelta(days=1)

    weekday_match = re.search(
        r"\b(?:(gelecek|onumuzdeki)\s+)?(pazartesi|sali|carsamba|persembe|cuma|cumartesi|pazar)\b",
        text,
    )
    if weekday_match:
        target_weekday = WEEKDAYS[weekday_match.group(2)]
        delta = (target_weekday - reference.weekday()) % 7
        if delta == 0:
            delta = 7 if weekday_match.group(1) else 0
        return reference.date() + timedelta(days=delta)

    found = search_dates(
        message,
        languages=["tr"],
        settings={
            "RELATIVE_BASE": reference,
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Europe/Istanbul",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )
    return found[0][1].date() if found else None


def resolve_temporal(message: str, reference: datetime) -> ResolvedTemporal:
    """Resolve one canonical Istanbul date/range/time before intent routing."""
    text = fold_turkish(message)
    time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text)
    target_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}" if time_match else None

    if "bu hafta sonu" in text or "hafta sonu" in text:
        days_to_saturday = (5 - reference.weekday()) % 7
        start = reference.date() + timedelta(days=days_to_saturday)
        if reference.weekday() == 6:
            start = reference.date() - timedelta(days=1)
        return ResolvedTemporal(start, start, start + timedelta(days=2), target_time, "bu hafta sonu")

    if "gelecek hafta" in text or "onumuzdeki hafta" in text:
        start = reference.date() + timedelta(days=(7 - reference.weekday()))
        return ResolvedTemporal(start, start, start + timedelta(days=7), target_time, "gelecek hafta")

    target = resolve_requested_date(message, reference)
    phrase = None
    if re.search(r"\bbugun\b", text):
        phrase = "bugün"
    elif re.search(r"\byarin\b", text):
        phrase = "yarın"
    elif "bu aksam" in text or "bu gece" in text:
        target = reference.date()
        phrase = "bu akşam"
    return ResolvedTemporal(target, target, target + timedelta(days=1) if target else None, target_time, phrase)
