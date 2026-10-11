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
    text = message.strip()

    quoted = re.search(r'["“](.+?)["”]', text)
    if quoted:
        return quoted.group(1).strip()

    text = re.sub(
        r'\b(?:takvimime|takvime|google takvime)\s+ekle\b.*$',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r'\b(?:\d{1,2}\s+(?:ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)(?:\s+\d{4})?)\b',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r'\b(?:saat\s*)?\d{1,2}(?::\d{2})?\b',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r'\b(?:bugün|bugun|yarın|yarin|akşam|aksam|sabah|öğlen|oglen)\b',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r'\b(?:bir tane|randevu oluşturdum|randevu olusturdum|randevu aldım|randevu aldim)\b',
        '',
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r'\s+', ' ', text).strip(' ,.-')
    return text or "NOVA etkinliği"


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
                f"Bora, ekledim. {created['title']} {decision.target_date.strftime('%d.%m.%Y')} saat {spoken_time} için {created['calendar']} takvimine kaydedildi."
            )

        return ActionResult(
            decision.action or "unknown",
            capability,
            False,
            False,
            "Bora, takvimde taşıma ve silme işlemlerini henüz güvenli eşleştirme olmadan çalıştırmıyorum."
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
