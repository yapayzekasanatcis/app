"""Modelsiz NOVA Core Intelligence V2 routing and memory contracts."""
import asyncio
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import assistant_context as context
from conversation_context import resolve_follow_up
from intelligence_models import _annotation_sources
from personal_memory import personal_memory_reply


NOW = datetime(2026, 10, 8, 12, tzinfo=ZoneInfo("Europe/Istanbul"))


@pytest.mark.parametrize(
    "question, expected_intent",
    [
        ("Tuğba'nın doğum günü?", "personal_memory"),
        ("Tuba'nın doğum günü ne zaman?", "personal_memory"),
        ("İstanbul'a genelde nasıl gitmek isterim?", "personal_memory"),
        ("Konserden sonra açık çorbacı bul.", "web_search"),
        ("Tuğba'nın ayakkabı numarası?", "unknown_fallback"),
        ("Türkiye'nin başkenti?", "general"),
        ("Bugünkü konser nerede?", "calendar_date_query"),
        ("17 Ekim Alanya için ulaşımımı araştır.", "travel_search"),
        ("İstanbul'a arabayla gidiyorum; dönüşüm gece. En mantıklı rota ne?", "travel_search"),
        ("Bekleyen işlerimi söyle.", "pending_tasks"),
        ("Bu hafta Komagene'de ne yapmam gerekiyor?", "weekly_routines"),
    ],
)
def test_router_uses_only_relevant_intents(question, expected_intent):
    intent, _target = context.classify_intent(question, NOW)
    assert intent == expected_intent


def test_unrelated_questions_never_fall_into_fixed_workspace_intents():
    forbidden = {"briefing", "today_schedule", "pending_tasks", "weekly_priorities"}
    for question in ("Tuğba'nın doğum günü?", "İstanbul'a genelde nasıl gitmek isterim?", "Tuğba'nın ayakkabı numarası?"):
        intent, _target = context.classify_intent(question, NOW)
        assert intent not in forbidden


def test_personal_memory_birthdays_food_and_unknown_are_deterministic():
    cases = {
        "Tuğba'nın doğum günü?": "10 Kasım 1990",
        "Atakan'ın doğum günü?": "11 Ocak",
        "Benim doğum günüm?": "12 Mayıs 1978",
        "Annemin doğum günü?": "13 Temmuz",
        "Tolga'nın doğum günü?": "29 Temmuz",
        "Ben hangi çorbaları severim?": "kaşarlı domates, mercimek ve ezogelin",
        "Tuğba'nın ayakkabı numarası?": "Bu bilgi bende kayıtlı değil, Bora.",
    }
    for question, expected in cases.items():
        result = personal_memory_reply(question, NOW)
        assert result and expected in result["reply"]


def test_vegetable_rule_never_recommends_a_vegetable_meal():
    result = personal_memory_reply("Sebze yemeği öner.", NOW)
    assert result
    assert "önermiyorum" in result["reply"]
    assert "köfte" in result["reply"].lower()


def test_calendar_follow_up_uses_previous_event_in_same_conversation():
    result = resolve_follow_up(
        "Peki kaçta?",
        {
            "intent": "calendar_date_query",
            "events": [{"title": "Sezon Açılış Konseri", "start": "2026-10-08T20:00:00+03:00", "location": "Merinos AKKM"}],
        },
    )
    assert result["intent"] == "conversation_context"
    assert "20:00" in result["reply"]


def test_weekly_priority_skips_non_actionable_social_event():
    events = [
        {"title": "Arkadaşlarla Konser", "description": "Sosyal", "start": "2026-10-09T20:00:00+03:00"},
        {"title": "Villa Verde Tiyatral Nikah", "description": "Hazırlık", "start": "2026-10-11T19:00:00+03:00"},
    ]
    answer = context.service_weekly_priorities(NOW, events, [], [])
    assert "Villa Verde" in answer
    assert "Arkadaşlarla Konser" not in answer


class _ContextCollection:
    async def find_one(self, *_args, **_kwargs):
        return None


class _FakeDb:
    conversation_contexts = _ContextCollection()


def test_personal_and_general_queries_do_not_load_workspace(monkeypatch):
    async def forbidden_workspace(*_args, **_kwargs):
        raise AssertionError("Workspace should not load for memory/general routes")

    monkeypatch.setattr(context, "load_workspace_source", forbidden_workspace)
    memory = asyncio.run(context.build_chat_package(_FakeDb(), "bora", "Tuğba'nın doğum günü?"))
    general = asyncio.run(context.build_chat_package(_FakeDb(), "bora", "Türkiye'nin başkenti?"))
    assert memory["intent"] == "personal_memory" and memory["reply"]
    assert general["intent"] == "general" and general["reply"] is None


def test_nested_grounding_metadata_is_normalized_to_sources():
    raw = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(annotations=[]))],
        model_dump=lambda: {
            "choices": [{
                "provider_specific_fields": {
                    "groundingMetadata": {
                        "groundingChunks": [{"web": {"title": "İDO", "uri": "https://example.com/ido"}}]
                    }
                }
            }]
        },
    )
    assert _annotation_sources(raw) == [{"title": "İDO", "url": "https://example.com/ido"}]