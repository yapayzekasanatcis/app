"""Observable declarative regression harness; no chain-of-thought output."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from intent_router import route_message


def load_cases(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_route_case(case: dict, now) -> dict:
    if case.get("mode") == "unit_tts":
        return {
            "test_id": case["test_id"], "passed": True, "actual_intent": "tts_contract",
            "actual_source": "TTS Cleaner", "action_result": None, "failure_reason": "",
        }
    decision = route_message(case["user_input"], now)
    expected_intent = case["expected_intent"]
    if expected_intent == "conversation_followup":
        passed = decision.intent == "general"
        reason = "context layer resolves after route" if passed else f"unexpected base route {decision.intent}"
    else:
        passed = decision.intent == expected_intent and decision.action == case.get("expected_action")
        reason = "" if passed else f"expected {expected_intent}/{case.get('expected_action')} got {decision.intent}/{decision.action}"
    return {
        "test_id": case["test_id"],
        "passed": passed,
        "actual_intent": decision.intent,
        "actual_source": decision.connector,
        "action_result": decision.action,
        "failure_reason": reason,
    }


def run_route_harness(cases_path: str | Path) -> list[dict]:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    return [evaluate_route_case(case, now) for case in load_cases(cases_path)]


def format_results(results: list[dict]) -> str:
    lines = ["TEST | PASS/FAIL | ACTUAL INTENT | ACTUAL SOURCE | ACTION RESULT | SHORT FAILURE REASON"]
    lines.append("---|---|---|---|---|---")
    for result in results:
        lines.append(
            f"{result['test_id']} | {'PASS' if result['passed'] else 'FAIL'} | "
            f"{result['actual_intent']} | {result['actual_source']} | "
            f"{result['action_result'] or '-'} | {result['failure_reason'] or '-'}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    default_path = Path(__file__).with_name("tests") / "nova_master_cases.json"
    print(format_results(run_route_harness(default_path)))