"""Verified action executor. Never claims success before reading the write back."""
from dataclasses import dataclass
import re

import google_integration as gint
from capability_registry import capability_message


@dataclass
class ActionResult:
    action: str
    capability: str
    executed: bool
    verified: bool
    reply: str

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "capability": self.capability,
            "executed": self.executed,
            "verified": self.verified,
        }


def _calendar_title(message: str) -> str:
    folded = message.casefold()

    if "gelin" in folded and "damat" in folded:
        return "Gelin-Damat Görüşmesi"

    if "tuğba" in folded or "tugba" in folded:
        if any(term in folded for term in ("sürpriz", "surpriz", "gizli", "hediye", "hazırlık", "hazirlik")):
            return "Tuğba — Sürpriz Hazırlık"

    quoted = re.search(r'["“](.+?)["”]', message)
    if quoted:
        return quoted.group(1).strip()

    text = message.strip()

    # Baştaki tarih + saat ifadesini temizle.
    text = re.sub(
        r'^\s*\d{1,2}\s+'
        r'(?:ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|'
        r'ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)'
        r'(?:\s+\d{4})?'
        r'(?:\s+saat)?\s+\d{1,2}(?::\d{2})?'
        r"(?:'?[ey]e|'?[ad]a)?\s*",
        '',
        text,
        flags=re.IGNORECASE,
    )

    # Komut kısmını temizle.
    text = re.sub(
        r'\b(?:takvimime|takvime|google takvime)\s+(?:ekle|kaydet|koy)\b.*$',
        '',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\b(?:ekle|kaydet|oluştur|olustur|eklenmesi)\b.*$',
        '',
        text,
        flags=re.IGNORECASE,
    )

    # Gizlilik talimatlarını başlıktan çıkar.
    text = re.sub(
        r'\b(?:gizli olsun|tuğba görmesin|tugba gormesin|sürpriz olsun|surpriz olsun)\b.*$',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r'\s+', ' ', text).strip(" ,.-'")

    return text or "NOVA Etkinliği"


async def execute_action(decision, registry: dict, db, user_id: str, message: str) -> ActionResult:
    if decision.intent == "calendar_action":
        capability = "calendar.write"
        unavailable = capability_message(registry, capability, "Google Calendar yazma")
        if unavailable:
            return ActionResult(decision.action or "unknown", capability, False, False, unavailable)

        if decision.action == "create":
            if not decision.target_date:
                return ActionResult(
                    "create", capability, False, False,
                    "Bora, takvime ekleyebilmem için hangi gün olduğunu net söylemen gerekiyor."
                )
            if not decision.target_time:
                return ActionResult(
                    "create", capability, False, False,
                    "Bora, günü anladım ama saat eksik. Saati söylersen takvime ekleyebilirim."
                )

            title = _calendar_title(message)
            created = await gint.create_calendar_event(
                db,
                user_id,
                title,
                decision.target_date,
                decision.target_time,
                message=message,
            )
            if not created:
                return ActionResult(
                    "create", capability, False, False,
                    "Bora, takvim kaydını oluşturamadım."
                )

            start_time = created.get("start", "")
            spoken_time = start_time[11:16] if len(start_time) >= 16 else decision.target_time

            return ActionResult(
                "create",
                capability,
                True,
                True,
                f"Bora, {created['title']} kaydını {decision.target_date.strftime('%d.%m.%Y')} saat {spoken_time} için {created['calendar']} takvimine ekledim."
            )

        if decision.action == "update":
            if not decision.target_date:
                return ActionResult(
                    "update", capability, False, False,
                    "Bora, hangi gündeki kaydı değiştireceğimi net söylemen gerekiyor."
                )
            if not decision.target_time:
                return ActionResult(
                    "update", capability, False, False,
                    "Bora, yeni saati de söylemen gerekiyor."
                )

            result = await gint.update_calendar_event_time(
                db,
                user_id,
                decision.target_date,
                decision.target_time,
                message,
            )

            if result.get("status") == "ambiguous":
                return ActionResult(
                    "update", capability, False, False,
                    "Bora, o gün birden fazla benzer kayıt buldum. Yanlış kaydı değiştirmemek için etkinliğin adını biraz daha net söyle."
                )
            if result.get("status") != "updated":
                return ActionResult(
                    "update", capability, False, False,
                    "Bora, değiştirmek istediğin takvim kaydını güvenli biçimde bulamadım."
                )

            return ActionResult(
                "update", capability, True, True,
                f"Bora, {result['title']} kaydını saat {result['time']} olarak güncelledim."
            )

        if decision.action == "delete":
            if not decision.target_date:
                return ActionResult(
                    "delete", capability, False, False,
                    "Bora, hangi gündeki kaydı sileceğimi net söylemen gerekiyor."
                )

            result = await gint.delete_calendar_event(
                db,
                user_id,
                decision.target_date,
                message,
            )

            if result.get("status") == "ambiguous":
                return ActionResult(
                    "delete", capability, False, False,
                    "Bora, o gün birden fazla benzer kayıt buldum. Yanlış kaydı silmemek için hangisi olduğunu biraz daha net söyle."
                )
            if result.get("status") != "deleted":
                return ActionResult(
                    "delete", capability, False, False,
                    "Bora, silmek istediğin takvim kaydını güvenli biçimde bulamadım."
                )

            return ActionResult(
                "delete", capability, True, True,
                f"Bora, {result['title']} kaydını takvimden sildim."
            )

        return ActionResult(
            decision.action or "unknown",
            capability,
            False,
            False,
            "Bora, bu takvim işlemini henüz güvenli biçimde yapamıyorum."
        )

    if decision.intent == "task_action":
        capability = "sheets.write"
        unavailable = capability_message(registry, capability, "NOVA İş Merkezi yazma")
        if unavailable:
            return ActionResult(decision.action or "unknown", capability, False, False, unavailable)

        status_map = {
            "complete": "Tamamlandı",
            "close": "Kapalı",
            "reopen": "Bekliyor",
        }

        if decision.action in status_map:
            result = await gint.update_task_status(
                db,
                user_id,
                message,
                status_map[decision.action],
            )
            if not result:
                return ActionResult(
                    decision.action,
                    capability,
                    False,
                    False,
                    "Bora, hangi görevi değiştirmemi istediğini İş Merkezi'nde güvenli biçimde eşleştiremedim."
                )
            if not result["verified"]:
                return ActionResult(
                    decision.action,
                    capability,
                    True,
                    False,
                    "Bora, göreve yazma yaptım ama sonucu doğrulayamadım; tamamlandı demiyorum."
                )

            return ActionResult(
                decision.action,
                capability,
                True,
                True,
                f"Bora, {result['task']} görevinin durumunu {result['status']} olarak güncelledim."
            )

        return ActionResult(
            decision.action or "unknown",
            capability,
            False,
            False,
            "Bora, bu görev yazma işlemi henüz güvenli yürütücüye bağlı değil."
        )

    return ActionResult(
        decision.action or "unknown",
        "none",
        False,
        False,
        "Bora, bu işlem için doğrulanmış bir yazma bağlantısı yok."
    )
