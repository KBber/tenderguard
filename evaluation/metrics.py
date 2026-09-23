"""Evaluation metrics for TenderGuard (spec §二十)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    case_id: str
    name: str
    expected_status: str
    actual_status: str
    expected_rule_passed: bool | None
    actual_rule_passed: bool | None
    matched: bool
    note: str = ""


@dataclass
class Metrics:
    cases: list[CaseResult] = field(default_factory=list)
    decision_accuracy: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0
    review_rate: float = 0.0
    total: int = 0
    passed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_accuracy": round(self.decision_accuracy, 3),
            "passed": self.passed,
            "total": self.total,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "review_rate": round(self.review_rate, 3),
            "per_case": [c.__dict__ for c in self.cases],
        }


def compute(cases: list[CaseResult]) -> Metrics:
    total = len(cases)
    passed = sum(1 for c in cases if c.matched)
    fp = sum(1 for c in cases if c.expected_status == "PASS" and c.actual_status != "PASS")
    fn = sum(1 for c in cases if c.expected_status == "FAIL" and c.actual_status != "FAIL")
    review = sum(1 for c in cases if c.actual_status == "REVIEW_REQUIRED")
    m = Metrics(
        cases=cases,
        decision_accuracy=passed / total if total else 0.0,
        false_positives=fp,
        false_negatives=fn,
        review_rate=review / total if total else 0.0,
        total=total,
        passed=passed,
    )
    return m