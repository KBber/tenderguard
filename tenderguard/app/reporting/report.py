"""Audit report v0.3: spec §十七.

10 sections:
  1. Executive Summary
  2. Critical Failures
  3. Requirement Coverage Matrix
  4. Cross-document Consistency
  5. Price Verification
  6. Product / Certificate Verification
  7. Evidence Quality
  8. Human Review Queue
  9. Rule Trace
  10. System Limitations
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections import Counter
from typing import Any

from tenderguard.app.schemas import (
    AuditReport,
    ChecklistItem,
    EvidenceQuality,
    RequirementCoverage,
    ReviewReason,
    ReviewType,
    Severity,
    VerificationResult,
    VerificationStatus,
)


_SEVERITY_ORDER = {
    (Severity.CRITICAL, VerificationStatus.FAIL): 0,
    (Severity.CRITICAL, VerificationStatus.REVIEW_REQUIRED): 1,
    (Severity.HIGH, VerificationStatus.FAIL): 2,
    (Severity.HIGH, VerificationStatus.REVIEW_REQUIRED): 3,
    (Severity.MEDIUM, VerificationStatus.FAIL): 4,
    (Severity.MEDIUM, VerificationStatus.REVIEW_REQUIRED): 5,
    (Severity.LOW, VerificationStatus.FAIL): 6,
    (Severity.LOW, VerificationStatus.REVIEW_REQUIRED): 7,
    (Severity.CRITICAL, VerificationStatus.PASS): 8,
    (Severity.HIGH, VerificationStatus.PASS): 9,
    (Severity.MEDIUM, VerificationStatus.PASS): 10,
    (Severity.LOW, VerificationStatus.PASS): 11,
    (Severity.CRITICAL, VerificationStatus.NOT_APPLICABLE): 12,
}


def _sort_key(r: VerificationResult) -> int:
    return _SEVERITY_ORDER.get((r.severity, r.status), 99)


def _summary(results: list[VerificationResult]) -> dict[str, int]:
    s = {"PASS": 0, "FAIL": 0, "REVIEW_REQUIRED": 0, "NOT_APPLICABLE": 0}
    for r in results:
        s[r.status.value] += 1
    return {
        "total": len(results), **s,
        "critical_fail": sum(1 for r in results if r.severity == Severity.CRITICAL and r.status == VerificationStatus.FAIL),
        "critical_review": sum(1 for r in results if r.severity == Severity.CRITICAL and r.status == VerificationStatus.REVIEW_REQUIRED),
        "high_fail": sum(1 for r in results if r.severity == Severity.HIGH and r.status == VerificationStatus.FAIL),
        "high_review": sum(1 for r in results if r.severity == Severity.HIGH and r.status == VerificationStatus.REVIEW_REQUIRED),
    }


def _decision_summary(items: list[ChecklistItem], results: list[VerificationResult]) -> dict[str, int]:
    machine_ids = {it.check_id for it in items if it.review_type not in (ReviewType.PROCESS_HUMAN, ReviewType.STRATEGY_HUMAN, ReviewType.EXTERNAL_DATA)}
    machine = [r for r in results if r.check_id in machine_ids]
    reliable = sum(1 for r in machine if r.status in (VerificationStatus.PASS, VerificationStatus.FAIL))
    return {
        "total_ck": len(results),
        "machine_capable_ck": len(machine_ids),
        "human_only_ck": len(results) - len(machine_ids),
        "reliable_machine_decisions": reliable,
        "machine_review_required": sum(1 for r in machine if r.status == VerificationStatus.REVIEW_REQUIRED),
        "fail_requiring_remediation": sum(1 for r in results if r.status == VerificationStatus.FAIL),
    }


def _failure_breakdown(results: list[VerificationResult]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for r in results:
        if r.status != VerificationStatus.REVIEW_REQUIRED:
            continue
        key = (r.review_reason or ReviewReason.MISSING_EVIDENCE).value
        counter[key] += 1
    return dict(counter)


def _evidence_quality_breakdown(results: list[VerificationResult]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for r in results:
        counter[r.evidence_quality.value] += 1
    return dict(counter)


def _review_type_breakdown(results: list[VerificationResult]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for r in results:
        counter[r.review_type.value] += 1
    return dict(counter)


def _evidence_table(results: list[VerificationResult]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    for r in results:
        for e in r.evidence:
            table.append({
                "check_id": r.check_id,
                "name": r.title,
                "document": e.document,
                "page": e.page,
                "locator": e.locator,
                "chunk_id": e.chunk_id,
                "quote": e.quote,
                "relevance": e.relevance,
                "quality": e.quality.value,
                "requirement_id": e.requirement_id,
                "source_type": e.source_type or ("tender" if "tender" in (e.doc_id or "") else "bid"),
            })
    return table


def _consistency_anomalies(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if r.status == VerificationStatus.FAIL and r.severity in (Severity.CRITICAL, Severity.HIGH):
            out.append({
                "check_id": r.check_id,
                "name": r.title,
                "severity": r.severity.value,
                "reason": r.reason,
                "rule_trace": r.rule_trace,
            })
    return out


def _recommendations(results: list[VerificationResult]) -> list[str]:
    recs: list[str] = []
    if any(r.status == VerificationStatus.FAIL and r.severity == Severity.CRITICAL for r in results):
        recs.append("存在 CRITICAL FAIL，建议在提交前完成整改。")
    if any(r.status == VerificationStatus.REVIEW_REQUIRED and r.severity == Severity.CRITICAL for r in results):
        recs.append("存在 CRITICAL REVIEW_REQUIRED 项目，必须由人工复核。")
    if any(r.status == VerificationStatus.FAIL and r.severity == Severity.HIGH for r in results):
        recs.append("存在 HIGH FAIL，建议优先处理。")
    if not recs:
        recs.append("未发现 CRITICAL/HIGH 失败，仍建议人工最终复核。")
    recs.append("本系统为决策辅助，最终结论由人工确认。")
    return recs


def _automation_breakdown(items: list[ChecklistItem], results: list[VerificationResult]) -> dict[str, int]:
    by_id = {it.check_id: it for it in items}
    breakdown: Counter[str] = Counter()
    for r in results:
        it = by_id.get(r.check_id)
        if it and it.review_type:
            breakdown[it.review_type.value] += 1
        else:
            breakdown["UNKNOWN"] += 1
    return dict(breakdown)


def _human_review_required(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if r.status != VerificationStatus.REVIEW_REQUIRED:
            continue
        out.append({
            "check_id": r.check_id,
            "name": r.title,
            "severity": r.severity.value,
            "review_type": r.review_type.value,
            "status": r.status.value,
            "review_reason": (r.review_reason or ReviewReason.MISSING_EVIDENCE).value,
            "review_question": r.review_question or "",
            "recommended_action": r.recommended_action or "",
            "reason": r.reason,
        })
    return out


# ---------------------------------------------------------------------------
# Section builders (spec §十七)
# ---------------------------------------------------------------------------


def _executive_summary(s: dict[str, int], ds: dict[str, int]) -> list[str]:
    return [
        f"共审核 {s['total']} 条 CK；其中 {ds['machine_capable_ck']} 条可机器判定（4 类 DOCUMENT_*），{ds['human_only_ck']} 条需人工。",
        f"机器可靠判定 {ds['reliable_machine_decisions']} 条；机器留待人工 {ds['machine_review_required']} 条；FAIL 需整改 {ds['fail_requiring_remediation']} 条。",
        f"Critical FAIL = {s['critical_fail']}；High FAIL = {s['high_fail']}。",
        "本系统为 Evidence-Grounded + Rule-Governed 合规审核，不做自动投标/提交/登录政府站。",
    ]


def _critical_failures(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if r.status == VerificationStatus.FAIL and r.severity == Severity.CRITICAL:
            out.append({
                "check_id": r.check_id,
                "name": r.title,
                "severity": r.severity.value,
                "reason": r.reason,
                "rule_trace": r.rule_trace,
                "review_question": r.review_question,
                "recommended_action": r.recommended_action,
            })
    return out


def _coverage_matrix(results: list[VerificationResult]) -> list[RequirementCoverage]:
    out: list[RequirementCoverage] = []
    for r in results:
        out.extend(r.requirement_coverage)
    return out


def _cross_doc_consistency(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if "consistency" in r.title.lower() or "一致性" in r.title or "整体" in r.title:
            out.append({
                "check_id": r.check_id,
                "name": r.title,
                "status": r.status.value,
                "reason": r.reason,
                "rule_trace": r.rule_trace,
            })
    return out


def _price_verification(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if any(k in r.title for k in ("报价", "分项报价", "小计", "限价", "金额")):
            calcs = (r.rule_trace or {}).get("calculations") or (r.rule_trace or {}).get("conflicts") or (r.rule_trace or {}).get("rows")
            out.append({
                "check_id": r.check_id,
                "name": r.title,
                "status": r.status.value,
                "reason": r.reason,
                "rule_trace": r.rule_trace,
                "calculations": calcs,
            })
    return out


def _product_cert_verification(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if any(k in r.title for k in ("资质", "产品", "彩页", "3C", "节能", "检测报告")):
            out.append({
                "check_id": r.check_id,
                "name": r.title,
                "status": r.status.value,
                "reason": r.reason,
                "rule_trace": r.rule_trace,
            })
    return out


def _human_review_queue(results: list[VerificationResult]) -> list[dict[str, Any]]:
    return _human_review_required(results)


def _rule_traces(results: list[VerificationResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        if not r.rule_trace:
            continue
        out.append({
            "check_run_id": r.check_run_id,
            "check_id": r.check_id,
            "name": r.title,
            "status": r.status.value,
            "rule_trace": r.rule_trace,
        })
    return out


def _system_limitations() -> list[str]:
    return [
        "P0 retrieval 使用 BM25-lite + CJK bigram；尚未升级到 BM25/向量 + reranker",
        "Extraction 仍为启发式 regex；部分长字段（如公司更名证明、报价表 XLSX）抽取精度受限",
        "未实装 LLM-backed fact extractor；HYBRID/SEMANTIC 项目在没有 LLM key 时回退到 REVIEW_REQUIRED",
        "A/B/C ablation 未实装（spec §二十）",
        "Excel 解析时 `_classify_v3` 是 deterministic keyword classifier；LLM-based classifier 可作为 P2 升级",
    ]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_report(
    items: list[ChecklistItem],
    results: list[VerificationResult],
    *,
    tender_document: str,
    bid_document: str,
    project: str = "",
    checklist_version: str = "v0.3",
) -> AuditReport:
    sorted_results = sorted(results, key=_sort_key)
    audit_id = f"audit-{uuid.uuid4().hex[:12]}"
    summary = _summary(sorted_results)
    return AuditReport(
        audit_id=audit_id,
        project=project,
        tender_document=tender_document,
        bid_document=bid_document,
        checklist_version=checklist_version,
        generated_at=_dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        decision_summary=_decision_summary(items, sorted_results),
        summary=summary,
        failure_breakdown=_failure_breakdown(sorted_results),
        evidence_quality_breakdown=_evidence_quality_breakdown(sorted_results),
        review_type_breakdown=_review_type_breakdown(sorted_results),
        executive_summary=_executive_summary(summary, _decision_summary(items, sorted_results)),
        critical_failures=_critical_failures(sorted_results),
        requirement_coverage_matrix=_coverage_matrix(sorted_results),
        cross_document_consistency=_cross_doc_consistency(sorted_results),
        price_verification=_price_verification(sorted_results),
        product_cert_verification=_product_cert_verification(sorted_results),
        human_review_queue=_human_review_queue(sorted_results),
        rule_traces=_rule_traces(sorted_results),
        system_limitations=_system_limitations(),
        results=sorted_results,
        evidence_table=_evidence_table(sorted_results),
        consistency_anomalies=_consistency_anomalies(sorted_results),
        recommendations=_recommendations(sorted_results),
        automation_breakdown=_automation_breakdown(items, sorted_results),
        human_review_required=_human_review_required(sorted_results),
    )


def render_markdown(report: AuditReport) -> str:
    s = report.summary
    ds = report.decision_summary
    fb = report.failure_breakdown
    eq = report.evidence_quality_breakdown
    rt = report.review_type_breakdown
    lines: list[str] = []
    lines.append(f"# TenderGuard v0.3 审核报告 — {report.project or '(未命名项目)'}")
    lines.append("")
    lines.append(f"- 招标文件：`{report.tender_document}`")
    lines.append(f"- 投标文件：`{report.bid_document}`")
    lines.append(f"- Checklist 版本：`{report.checklist_version}`")
    lines.append(f"- Audit ID：`{report.audit_id}`")
    lines.append(f"- 生成时间：`{report.generated_at}`")
    lines.append("")
    lines.append("## 1. Executive Summary")
    for line in report.executive_summary:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("### Decision Summary")
    lines.append(f"- Total CK: **{ds['total_ck']}**")
    lines.append(f"- Machine-capable CK: **{ds['machine_capable_ck']}**")
    lines.append(f"- Human-only CK: **{ds['human_only_ck']}**")
    lines.append(f"- Reliable machine decisions (PASS+FAIL): **{ds['reliable_machine_decisions']}**")
    lines.append(f"- Machine Review Required: **{ds['machine_review_required']}**")
    lines.append(f"- FAIL requiring remediation: **{ds['fail_requiring_remediation']}**")
    lines.append("")
    lines.append("### 整体风险")
    lines.append(f"- PASS: **{s['PASS']}** | FAIL: **{s['FAIL']}** | REVIEW_REQUIRED: **{s['REVIEW_REQUIRED']}** | N/A: **{s['NOT_APPLICABLE']}**")
    lines.append(f"- CRITICAL FAIL: **{s['critical_fail']}** | CRITICAL REVIEW: **{s['critical_review']}**")
    lines.append(f"- HIGH FAIL: **{s['high_fail']}** | HIGH REVIEW: **{s['high_review']}**")
    lines.append("")

    lines.append("## 2. Critical Failures")
    if report.critical_failures:
        for c in report.critical_failures:
            lines.append(f"- **{c['check_id']}** {c['name']} — {c['reason'][:120]}")
            if c.get("review_question"):
                lines.append(f"  - 问：{c['review_question']}")
            if c.get("recommended_action"):
                lines.append(f"  - 建议：{c['recommended_action']}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 3. Requirement Coverage Matrix")
    if report.requirement_coverage_matrix:
        lines.append("| req_id | requirement | verification | coverage | decision | reason |")
        lines.append("|---|---|---|---|---|---|")
        for cov in report.requirement_coverage_matrix[:50]:
            req = cov.requirement.replace("|", "\\|")[:80]
            reason = (cov.reason or "").replace("|", "\\|")[:80]
            lines.append(f"| {cov.requirement_id} | {req} | {cov.verification.value} | {cov.coverage} | {cov.decision} | {reason} |")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 4. Cross-document Consistency")
    if report.cross_document_consistency:
        for c in report.cross_document_consistency:
            lines.append(f"- **{c['check_id']}** {c['name']} — status={c['status']} | {c['reason'][:120]}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 5. Price Verification")
    if report.price_verification:
        for c in report.price_verification:
            lines.append(f"- **{c['check_id']}** {c['name']} — status={c['status']} | {c['reason'][:120]}")
            calcs = c.get("calculations")
            if calcs and isinstance(calcs, list):
                lines.append(f"  - calculations: {len(calcs)} row(s)")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 6. Product / Certificate Verification")
    if report.product_cert_verification:
        for c in report.product_cert_verification:
            lines.append(f"- **{c['check_id']}** {c['name']} — status={c['status']} | {c['reason'][:120]}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 7. Evidence Quality")
    if eq:
        for k, v in sorted(eq.items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## 8. Human Review Queue")
    if report.human_review_queue:
        for h in report.human_review_queue:
            lines.append(f"- **{h['check_id']}** {h['name']} ({h['severity']}, {h['review_type']}) | reason=`{h['review_reason']}`")
            lines.append(f"  - 问：{h['review_question']}")
            lines.append(f"  - 建议：{h['recommended_action']}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 9. Rule Trace (前 20 条)")
    if report.rule_traces:
        lines.append("| check_run_id | check_id | status | rule_trace |")
        lines.append("|---|---|---|---|")
        for r in report.rule_traces[:20]:
            rt_str = json.dumps(r["rule_trace"], ensure_ascii=False)[:200].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['check_run_id']} | {r['check_id']} | {r['status']} | {rt_str} |")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 10. System Limitations")
    for line in report.system_limitations:
        lines.append(f"- {line}")
    lines.append("")

    lines.append("## 11. Failure Breakdown (by ReviewReason)")
    if fb:
        for k, v in sorted(fb.items(), key=lambda x: -x[1]):
            lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## 12. Review Type Breakdown")
    lines.append("")
    lines.append("| review_type | count |")
    lines.append("|---|---|")
    for k, v in sorted(rt.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## 13. Detailed Results")
    lines.append("")
    lines.append("| check_id | severity | review_type | status | method | evidence_quality | review_reason | title |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report.results:
        rr = (r.review_reason or "-").value if r.review_reason else "-"
        lines.append(f"| {r.check_id} | {r.severity.value} | {r.review_type.value} | {r.status.value} | {r.method.value} | {r.evidence_quality.value} | {rr} | {r.title[:30]} |")
    lines.append("")

    lines.append("---")
    lines.append("> 本系统为决策辅助，最终结论由人工确认。")
    return "\n".join(lines) + "\n"


import json  # placed here to avoid top-of-file circular import