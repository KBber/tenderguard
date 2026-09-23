"""Evaluation runner: feed each case through the real pipeline and compare."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tenderguard.app.checklists.loader import load_checklist
from tenderguard.app.extraction.facts import extract_facts
from tenderguard.app.reporting.report import build_report
from tenderguard.app.rules.engine import run_rule
from tenderguard.app.schemas import (
    ChecklistItem,
    DocumentChunk,
    Severity,
    VerificationMethod,
    VerificationStatus,
)
from tenderguard.app.verification.verifier import VerifyContext, verify_item
from tenderguard.app.extraction.llm import LLMClient

from evaluation.metrics import CaseResult, Metrics, compute


def _chunks_from_texts(tender: str, bid: str) -> list[DocumentChunk]:
    return [
        DocumentChunk(doc_id="tender", document="tender.pdf", page=1, section=None, text=tender),
        DocumentChunk(doc_id="bid", document="bid.pdf", page=1, section=None, text=bid),
    ]


def _make_item(case: dict) -> ChecklistItem:
    return ChecklistItem(
        check_id=case["case_id"],
        category="evaluation",
        name=case.get("name", case["case_id"]),
        description=case.get("name", case["case_id"]),
        severity=Severity.HIGH,
        verification_method=VerificationMethod.DETERMINISTIC,
        evidence_required=[],
        rule=case.get("rule"),
        source_sheet="evaluation_cases",
        source_row=0,
        original_requirement=case.get("name", ""),
        automation_level="FULL",
    )


def run(cases_path: str | Path = ROOT / "evaluation" / "cases.json") -> Metrics:
    raw = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    results: list[CaseResult] = []
    for c in raw["cases"]:
        chunks = _chunks_from_texts(c.get("tender", ""), c.get("bid", ""))
        facts = extract_facts(chunks)
        ctx = VerifyContext(chunks=chunks, facts=facts, llm=LLMClient())
        item = _make_item(c)
        rule_passed: bool | None = None
        if item.rule:
            r = run_rule(item.rule, facts)
            rule_passed = r.passed
        v = verify_item(item, ctx)
        matched = v.status.value == c["expected_status"]
        results.append(CaseResult(
            case_id=c["case_id"],
            name=c.get("name", c["case_id"]),
            expected_status=c["expected_status"],
            actual_status=v.status.value,
            expected_rule_passed=c.get("expected_rule_passed"),
            actual_rule_passed=rule_passed,
            matched=matched,
            note=v.reason[:80],
        ))
    m = compute(results)
    return m


if __name__ == "__main__":
    metrics = run()
    print(f"decision_accuracy={metrics.decision_accuracy} ({metrics.passed}/{metrics.total})")
    print(f"false_positives={metrics.false_positives}  false_negatives={metrics.false_negatives}")
    print(f"review_rate={metrics.review_rate}")
    for c in metrics.cases:
        mark = "OK " if c.matched else "FAIL"
        print(f"  [{mark}] {c.case_id} {c.name[:50]:50s} expected={c.expected_status:18s} actual={c.actual_status:18s}")