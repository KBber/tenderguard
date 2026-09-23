"""Evaluation runner v0.3: 60 cases + 9 metrics."""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenderguard.app.checklists.loader import load_checklist
from tenderguard.app.extraction.facts import extract_facts
from tenderguard.app.extraction.llm import LLMClient
from tenderguard.app.rules.engine import run_rule
from tenderguard.app.schemas import (
    ChecklistItem,
    DocumentChunk,
    Severity,
    VerificationMethod,
    VerificationStatus,
)
from tenderguard.app.verification.verifier import VerifyContext, verify_item


@dataclass
class CaseResult:
    case_id: str
    scenario: str
    expected_status: str
    actual_status: str
    expected_rule_passed: bool | None
    actual_rule_passed: bool | None
    expected_review_reason: str | None
    actual_review_reason: str | None
    matched: bool
    abstained_correctly: bool = False


@dataclass
class Metrics:
    total: int = 0
    decision_correct: int = 0
    decision_accuracy: float = 0.0
    true_pass: int = 0
    true_fail: int = 0
    true_review: int = 0
    false_positive: int = 0  # expected PASS but actual != PASS
    false_negative: int = 0  # expected FAIL but actual != FAIL
    abstention_accuracy: float = 0.0
    abstained_correctly: int = 0
    abstention_total: int = 0
    category_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)


def _chunks_from_texts(tender: str, bid: str) -> list[DocumentChunk]:
    return [
        DocumentChunk(doc_id="tender", document="tender.pdf", page=1, section=None, text=tender),
        DocumentChunk(doc_id="bid", document="bid.pdf", page=1, section=None, text=bid),
    ]


def _make_item(case: dict) -> ChecklistItem:
    return ChecklistItem(
        check_id=case["case_id"],
        title=case.get("scenario", case["case_id"])[:40],
        source_text=case.get("scenario", case["case_id"]),
        category="evaluation",
        severity=Severity.HIGH,
        review_type="DOCUMENT_DETERMINISTIC",
        classification_reason="evaluation fixture",
        rule=case.get("rule"),
        verification_method=VerificationMethod.DETERMINISTIC,
        evidence_required=[],
    )


def _classify_expected(case: dict) -> str:
    expected = case.get("expected_status", "")
    if expected in {"PASS", "FAIL"}:
        return "verifiable"
    reason = case.get("expected_review_reason", "")
    if "MISSING" in reason or "EXTRACTION" in reason or "TABLE" in reason:
        return "evidence_missing"
    if "CONFLICT" in reason:
        return "conflict"
    if "REQUIREMENT_UNRESOLVED" in reason:
        return "ambiguous"
    return "other"


def run(cases_path: str | Path = ROOT / "evaluation" / "cases_v3.json") -> Metrics:
    raw = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    results: list[CaseResult] = []
    for c in raw["cases"]:
        chunks = _chunks_from_texts(c.get("tender", ""), c.get("bid", ""))
        facts = extract_facts(chunks)
        ctx = VerifyContext(chunks=chunks, facts=facts, llm=LLMClient())
        item = _make_item(c)
        actual_rule_passed: bool | None = None
        if item.rule:
            rr = run_rule(item.rule, facts)
            actual_rule_passed = rr.passed
        v = verify_item(item, ctx)
        actual_status = v.status.value
        matched = (actual_status == c.get("expected_status"))
        # abstention correctness: expected REVIEW_REQUIRED and actual is REVIEW_REQUIRED
        abstained = (c.get("expected_status") == "REVIEW_REQUIRED" and actual_status == "REVIEW_REQUIRED")
        results.append(CaseResult(
            case_id=c["case_id"],
            scenario=c.get("scenario", ""),
            expected_status=c.get("expected_status", ""),
            actual_status=actual_status,
            expected_rule_passed=c.get("expected_rule_passed"),
            actual_rule_passed=actual_rule_passed,
            expected_review_reason=c.get("expected_review_reason"),
            actual_review_reason=(v.review_reason.value if v.review_reason else None),
            matched=matched,
            abstained_correctly=abstained,
        ))

    m = Metrics()
    m.total = len(results)
    m.decision_correct = sum(1 for r in results if r.matched)
    m.decision_accuracy = m.decision_correct / m.total if m.total else 0.0
    m.true_pass = sum(1 for r in results if r.expected_status == "PASS" and r.matched)
    m.true_fail = sum(1 for r in results if r.expected_status == "FAIL" and r.matched)
    m.true_review = sum(1 for r in results if r.expected_status == "REVIEW_REQUIRED" and r.matched)
    m.false_positive = sum(1 for r in results if r.expected_status == "PASS" and r.actual_status != "PASS")
    m.false_negative = sum(1 for r in results if r.expected_status == "FAIL" and r.actual_status != "FAIL")
    m.abstention_total = sum(1 for r in results if r.expected_status == "REVIEW_REQUIRED")
    m.abstained_correctly = sum(1 for r in results if r.abstained_correctly)
    m.abstention_accuracy = m.abstained_correctly / m.abstention_total if m.abstention_total else 0.0

    # Category breakdown
    cats = Counter(_classify_expected(c) for c in raw["cases"])
    by_cat_correct = Counter()
    for c, r in zip(raw["cases"], results):
        cat = _classify_expected(c)
        if r.matched:
            by_cat_correct[cat] += 1
    m.category_breakdown = {
        k: {"total": cats[k], "correct": by_cat_correct[k]}
        for k in cats
    }
    return m


if __name__ == "__main__":
    metrics = run()
    print(f"decision_accuracy = {metrics.decision_accuracy:.3f} ({metrics.decision_correct}/{metrics.total})")
    print(f"  true_pass={metrics.true_pass}  true_fail={metrics.true_fail}  true_review={metrics.true_review}")
    print(f"  false_positive={metrics.false_positive}  false_negative={metrics.false_negative}")
    print(f"abstention_accuracy = {metrics.abstention_accuracy:.3f} ({metrics.abstained_correctly}/{metrics.abstention_total})")
    print("category_breakdown:")
    for k, v in metrics.category_breakdown.items():
        print(f"  {k:20s}: {v['correct']}/{v['total']}")
    print()
    print("case detail:")
    raw = json.loads(Path(ROOT / "evaluation" / "cases_v3.json").read_text(encoding="utf-8"))
    metrics2 = run()
    for i, (c, r) in enumerate(zip(raw["cases"], [
        CaseResult(c["case_id"], c.get("scenario",""), c.get("expected_status",""),
                   "?", c.get("expected_rule_passed"), None, c.get("expected_review_reason"), None, False)
        for c in raw["cases"]
    ])):
        pass
    # Re-run for fresh actual
    from tenderguard.app.verification.verifier import verify_item, VerifyContext
    from tenderguard.app.extraction.llm import LLMClient
    for c in raw["cases"]:
        chunks = _chunks_from_texts(c.get("tender",""), c.get("bid",""))
        facts = extract_facts(chunks)
        ctx = VerifyContext(chunks=chunks, facts=facts, llm=LLMClient())
        item = _make_item(c)
        v = verify_item(item, ctx)
        mark = "OK " if v.status.value == c.get("expected_status") else "FAIL"
        print(f"  [{mark}] {c['case_id']} expected={c.get('expected_status',''):18s} actual={v.status.value:18s} {c.get('scenario','')[:60]}")