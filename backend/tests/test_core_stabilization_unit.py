"""Focused unit contracts for Core Stabilization V3."""
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from action_executor import execute_action
from capability_registry import get_capability_registry
from intent_router import route_message
from response_composer import (
    apply_freshness_guard,
    classify_calendar_event,
    compose_calendar_answer,
    ensure_requested_items,
)


NOW = datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("Europe/Istanbul"))


def test_memory_support_does_not_replace_birthday_planning():
    decision = route_message("Tuğba'nın doğum günü için 15.000 TL bütçeyle 3 plan hazırla.", NOW)
    assert decision.intent == "planning"
    assert "tugba" in decision.memory_context_keys


def test_tomorrow_briefing_keeps_tomorrow_target():
    decision = route_message("Yarın için kısa brifing hazırla.", NOW)
    assert decision.intent == "briefing"
    assert decision.target_date == date(2026, 10, 10)


def test_exact_source_targets_are_preserved():
    projects = route_message("NOVA İş Merkezi'ndeki Projeler sayfasına bak.", NOW)
    docs = route_message("Docs'taki NOVA ASİSTAN — ÇEKİRDEK KURALLAR VE RUTİNLER belgesini aç.", NOW)
    assert projects.connector == "sheets" and projects.target_tab == "Projeler"
    assert docs.connector == "docs" and "Çekirdek" in docs.target_document


def test_komagene_routine_is_non_blocking():
    event = {"title": "Komagene Sevkiyat Günü", "start": "2026-10-10", "description": "All day"}
    assert classify_calendar_event(event) == "non_blocking_routine"


def test_tiyatral_nikah_is_blocking():
    event = {"title": "Tiyatral Nikâh", "start": "2026-10-11T19:00:00+03:00"}
    assert classify_calendar_event(event) == "blocking"


def test_calendar_composer_is_natural_and_short():
    answer = compose_calendar_answer(
        date(2026, 10, 11),
        [{
            "title": "Villa Verde Tiyatral Nikâh",
            "location": "Villa Verde, Mudanya, Bursa",
            "start": "2026-10-11T19:00:00+03:00",
            "description": "Nikâh saati: 20:00",
        }],
        True,
        "11 Ekim'de ne işim var?",
    )
    assert "19:00" in answer and "20:00" in answer
    assert "Villa Verde" in answer and "description" not in answer


def test_old_price_is_not_used_as_current_total():
    answer = "2024 KGM geçiş ücreti 995 TL.\n2026 sürüş süresi yaklaşık 2 saat."
    guarded = apply_freshness_guard(answer, 2026, True)
    assert "995 TL" not in guarded
    assert "Eski fiyatları" in guarded


def test_requested_mode_completion_guard_names_missing_mode():
    answer = ensure_requested_items("Özel araç ve otobüs seçenekleri doğrulandı.", ["özel araç", "otobüs", "deniz yolu"])
    assert "deniz yolu" in answer


class _Collection:
    async def find_one(self, *_args, **_kwargs):
        return None


class _Db:
    google_tokens = _Collection()


def test_capability_registry_never_assumes_google_or_gmail_access():
    registry = asyncio.run(get_capability_registry(_Db(), "unit-no-token", force=True))
    assert registry["calendar.read"]["available"] is False
    assert registry["gmail.read"]["available"] is False
    assert registry["calendar.write"]["available"] is False
    assert registry["sheets.write"]["available"] is False


def test_readonly_action_never_claims_success():
    decision = route_message("Yarın 20:00'ye NOVA Test Etkinliği ekle.", NOW)
    registry = {"calendar.write": {"granted": False, "available": False, "runtime": "not_granted"}}
    result = asyncio.run(execute_action(decision, registry))
    assert result.executed is False and result.verified is False
    assert not any(word in result.reply for word in ("Ekledim", "Güncelledim", "Sildim"))