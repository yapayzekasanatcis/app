"""Turkish text and STT-noise intent classification regression tests."""
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assistant_context import classify_intent


REFERENCE = datetime(2026, 10, 8, 12, tzinfo=ZoneInfo("Europe/Istanbul"))


def test_supported_turkish_voice_variations():
    cases = {
        "bugün programım ne": "today_schedule",
        "bugünkü programım ne": "today_schedule",
        "bugün ne var": "today_schedule",
        "günün programını söyle": "today_schedule",
        "briefingimi oku": "briefing",
        "brifingimi oku": "briefing",
        "günün özetini oku": "briefing",
        "bekleyen işlerimi oku": "pending_tasks",
        "bekleyen görevlerim ne": "pending_tasks",
    }
    for phrase, expected in cases.items():
        intent, _target = classify_intent(phrase, REFERENCE)
        assert intent == expected, phrase


def test_typical_stt_errors_keep_meaning():
    cases = {
        "Nova, dünün briefingini sesle oku": "briefing",
        "NOVA BU GÖNKÜ PROGRAMI NE": "today_schedule",
        "bekliyen gorevlerimi oku": "pending_tasks",
        "gunun birifingini sesli oku": "briefing",
        "bugunki porogramim ne": "today_schedule",
    }
    for phrase, expected in cases.items():
        intent, _target = classify_intent(phrase, REFERENCE)
        assert intent == expected, phrase
