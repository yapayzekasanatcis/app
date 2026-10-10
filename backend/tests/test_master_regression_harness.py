"""Unit routing half of the 30-case master harness."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from regression_harness import evaluate_route_case, load_cases


CASES = load_cases(Path(__file__).with_name("nova_master_cases.json"))
NOW = datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("Europe/Istanbul"))


@pytest.mark.parametrize("case", CASES, ids=[case["test_id"] for case in CASES])
def test_master_route_contract(case):
    result = evaluate_route_case(case, NOW)
    print(result)
    assert result["passed"], result


def test_write_cases_are_unit_only_and_never_report_connector_success():
    write_cases = [case for case in CASES if case.get("expected_action")]
    assert {case["test_id"] for case in write_cases} == {"M16", "N17", "O18"}
    assert all("verify_before_success" in case["assertions"] or "flexible_task" in case["assertions"] for case in write_cases)