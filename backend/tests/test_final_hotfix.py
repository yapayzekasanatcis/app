"""Modelsiz final hotfix routing, TTS and answer-cleaning contracts."""
from datetime import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from assistant_context import classify_intent
from intelligence_models import WEB_FAILURE, clean_web_answer
from server import prepare_tts_text


NOW = datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("Europe/Istanbul"))


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Bu hafta sonu Tuğba'yla Eskişehir'e iki günlük gezi planla.", "travel_search"),
        ("Yalova Termal'de iki kişilik otel araştır.", "hotel_search"),
        ("17 Ekim Alanya için Obilet'ten gidiş dönüş otobüs araştır.", "travel_search"),
        ("Antalya için Pegasus ve THY uçuşlarını araştır.", "travel_search"),
        ("Bu akşam Bursa'da yemek yiyelim.", "restaurant_search"),
        ("23:00 sonrası mercimek/kaşarlı domates çorbası bul.", "restaurant_search"),
        ("Yarın Tuğba'yla sinemaya gidelim.", "cinema_search"),
        ("Bu hafta sonu Bursa'da konser/tiyatro araştır.", "event_search"),
        ("Yarın Bursa'da 5 saatlik plan yap.", "leisure_search"),
        ("11 Ekim'de etkinliğim nerede?", "calendar_date_query"),
    ],
)
def test_main_intent_beats_time_expression(question, expected):
    intent, _target = classify_intent(question, NOW)
    assert intent == expected


def test_web_answer_removes_raw_sources_but_keeps_labels():
    raw = "İlk seçenek [Kadim Restaurant](https://example.com/redirect).\n\nKaynaklar:\n- https://example.com"
    cleaned = clean_web_answer(raw)
    assert cleaned == "İlk seçenek Kadim Restaurant."
    assert "http" not in cleaned


def test_tts_removes_urls_citations_and_reads_turkish_clock():
    text = "Program 20:00'de. [Kaynak](https://example.com/a)\n\nKaynaklar:\n- https://example.com"
    prepared = prepare_tts_text(text)
    assert "saat yirmi" in prepared
    assert "http" not in prepared
    assert "Kaynaklar" not in prepared
    assert "sıfır sıfır" not in prepared


def test_tts_half_hour_is_natural_turkish():
    assert "saat on dokuz otuz" in prepare_tts_text("Başlangıç 19:30.")


def test_live_failure_is_explicit_and_non_generic():
    assert WEB_FAILURE == "Bu bilgiyi canlı kaynaktan doğrulayamadım, Bora."