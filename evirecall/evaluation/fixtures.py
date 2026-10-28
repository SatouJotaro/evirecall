"""Evaluator-only expectations for synthetic setup fixtures, not benchmark metrics."""

from dataclasses import dataclass
import json
from pathlib import Path

from evirecall.contracts import ContractError, EpisodeResult, check_fields, require_text


@dataclass(frozen=True)
class FixtureExpectation:
    task_id: str
    expected_status: str
    expected_prediction: str | None
    expected_source_ids: tuple[str, ...]


def load_expectations(path: Path) -> dict[str, FixtureExpectation]:
    expectations = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        check_fields(data, {"task_id", "expected_status", "expected_prediction", "expected_source_ids"})
        require_text(data["task_id"], "task_id")
        if data["task_id"] in expectations:
            raise ContractError("Duplicate evaluator task ID")
        if data["expected_status"] not in ("completed", "abstained", "failed"):
            raise ContractError("Invalid expected status")
        if data["expected_prediction"] is not None:
            require_text(data["expected_prediction"], "expected_prediction")
        if not isinstance(data["expected_source_ids"], list):
            raise ContractError("expected_source_ids must be an array")
        data["expected_source_ids"] = tuple(require_text(x, "source_id") for x in data["expected_source_ids"])
        expectations[data["task_id"]] = FixtureExpectation(**data)
    return expectations


def score_fixture(result: EpisodeResult, expected: FixtureExpectation) -> dict:
    sources = {source for item in result.evidence.items for source in item.source_ids}
    checks = {
        "terminal_status": result.status == expected.expected_status,
        "fixture_output": result.prediction == expected.expected_prediction,
        "source_ids": sources == set(expected.expected_source_ids),
    }
    return {"task_id": result.task_id, "passed": all(checks.values()), "checks": checks}
