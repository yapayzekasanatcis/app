"""Verified action gate; never claims success without persistent write verification."""
from dataclasses import dataclass

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


async def execute_action(decision, registry: dict) -> ActionResult:
    if decision.intent == "calendar_action":
        capability = "calendar.write"
        unavailable = capability_message(registry, capability, "Google Calendar yazma")
        return ActionResult(decision.action or "unknown", capability, False, False, unavailable or "Bora, Calendar write bu sürümde güvenli biçimde devre dışı.")
    if decision.intent == "task_action":
        capability = "sheets.write"
        unavailable = capability_message(registry, capability, "NOVA İş Merkezi yazma")
        return ActionResult(decision.action or "unknown", capability, False, False, unavailable or "Bora, Sheets write bu sürümde güvenli biçimde devre dışı.")
    return ActionResult(decision.action or "unknown", "none", False, False, "Bora, bu işlem için doğrulanmış bir write connector yok.")