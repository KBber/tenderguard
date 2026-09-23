"""Verification pipeline (v0.3: spec §七/§八/§十一).

For each checklist item:
  0. Check preconditions (spec §八). If any precondition fails → INSUFFICIENT_EVIDENCE
  1. Run rule (authoritative; spec §四 / §十)
  2. Aggregate evidence_quality across all retrieved evidence
  3. Decision logic:
     - DOCUMENT_DETERMINISTIC items: rule result is final (with hard-rule whitelist)
     - DOCUMENT_HYBRID / SEMANTIC items: LLM fallback if rule is None
     - CRITICAL/HIGH + status PASS but quality < DIRECT → downgrade REVIEW_REQUIRED
     - CONFLICTING evidence always → REVIEW_REQUIRED
  4. Attach review_reason + review_question + recommended_action (spec §十六)
  5. Bind evidence to atomic_requirements (spec §六)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from tenderguard.app.extraction.facts import extract_facts
from tenderguard.app.extraction.llm import LLMClient, LLMUnavailable
from tenderguard.app.retrieval.keyword import retrieve
from tenderguard.app.rules.engine import RuleResult, run_rule
from tenderguard.app.schemas import (
    ChecklistItem,
    DocumentChunk,
    Evidence,
    EvidenceQuality,
    RequirementCoverage,
    ReviewReason,
    ReviewType,
    VerificationMethod,
    VerificationResult,
    VerificationStatus,
)


_HARD_RULES_NEVER_OVERRIDDEN = frozenset({
    "same_model_same_price", "sum_equals",
    "equals", "not_equals",
    "numeric_gt", "numeric_gte", "numeric_lt", "numeric_lte",
    "date_before", "date_after",
    "count_gte",
    "required", "exists",
    "contains", "not_contains", "regex",
    "same_value", "field_consistency",
})


@dataclass
class VerifyContext:
    chunks: list[DocumentChunk]
    facts: dict[str, Any]
    llm: LLMClient
    audit_id: str = ""
    prompt_path: str = ""


# ---------------------------------------------------------------------------
# Precondition check (spec §八)
# ---------------------------------------------------------------------------


def _check_preconditions(item: ChecklistItem, facts: dict[str, Any]) -> tuple[bool, list[str]]:
    """Each precondition.expression is a dotted path or simple assertion.

    Supported forms:
      - "facts.a.b != null"      (presence + non-empty)
      - "facts.a is not None"
      - "bid.price_rows is not empty"
      - "a.b"  (presence + non-empty)
    Returns (all_pass, list_of_failed_expressions).
    """

    failed: list[str] = []
    for pre in item.preconditions:
        expr = pre.expression
        # Accept "facts.a.b" / "a.b" / "a.b is not empty" / "a.b != null"
        m = re.search(r"(?:facts\.)?([\w][\w\.]*)", expr)
        if not m:
            continue
        dotted = m.group(1)
        try:
            v = _dotted_get(facts, dotted)
        except KeyError:
            failed.append(expr)
            continue
        if v is None or v == "" or (isinstance(v, (list, dict)) and len(v) == 0):
            failed.append(expr)
    return len(failed) == 0, failed


def _dotted_get(facts: dict[str, Any], dotted: str) -> Any:
    if dotted in facts:
        return facts[dotted]
    cur: Any = facts
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(dotted)
    return cur


# ---------------------------------------------------------------------------
# Path -> Chinese keyword expansion for retrieval query
# ---------------------------------------------------------------------------


_PATH_KEYWORDS: dict[str, str] = {
    "project_name": "项目名称",
    "project_id": "项目编号",
    "package_id": "包号",
    "bidder_name": "投标人 名称 营业执照",
    "legal_representative": "法人代表",
    "authorized_person": "被授权人",
    "amount": "金额",
    "payee": "收款",
    "total_price": "总价 合计",
    "price_ceiling": "限价 拦标价",
    "contract_amount": "合同 金额",
    "name": "名称",
    "number": "编号",
    "company_name": "公司名称",
    "test_report_name": "检测报告 名称",
    "test_report_no": "报告编号",
}


def _path_to_chinese(dotted: str) -> list[str]:
    out: list[str] = []
    for part in dotted.split("."):
        out.extend(_PATH_KEYWORDS.get(part, part).split())
    return out


def _query_for(item: ChecklistItem) -> str:
    parts = [item.title, item.source_text]
    # include atomic requirement descriptions to widen the query
    for r in item.atomic_requirements or []:
        parts.append(r.description)
    rule = item.rule or {}
    for key in ("fields", "actual_field", "required_field"):
        v = rule.get(key)
        if isinstance(v, str):
            parts.extend(_path_to_chinese(v))
        elif isinstance(v, list):
            for f in v:
                if isinstance(f, str):
                    parts.extend(_path_to_chinese(f))
    for pair in rule.get("pairs", []) or []:
        for f in pair:
            if isinstance(f, str):
                parts.extend(_path_to_chinese(f))
    return " ".join(p for p in parts if p)


def _doc_filter_for(item: ChecklistItem) -> list[str] | None:
    """For DOCUMENT_* types, search both docs; for human-only don't search."""
    if item.review_type in (ReviewType.PROCESS_HUMAN, ReviewType.STRATEGY_HUMAN, ReviewType.EXTERNAL_DATA):
        return ["tender", "bid"]
    if item.review_type == ReviewType.DOCUMENT_SEMANTIC:
        return ["tender", "bid"]
    return ["tender", "bid"]


def _aggregate_evidence_quality(evidence: list[Evidence]) -> EvidenceQuality:
    if not evidence:
        return EvidenceQuality.MISSING
    q = {e.quality for e in evidence}
    if EvidenceQuality.CONFLICTING in q:
        return EvidenceQuality.CONFLICTING
    if EvidenceQuality.DIRECT in q:
        return EvidenceQuality.DIRECT
    if EvidenceQuality.SUPPORTING in q:
        return EvidenceQuality.SUPPORTING
    if EvidenceQuality.INDIRECT in q:
        return EvidenceQuality.INDIRECT
    return EvidenceQuality.WEAK


def _confidence(status: VerificationStatus, rule_passed: bool | None, eq: EvidenceQuality) -> float:
    base = 0.92 if rule_passed is True else 0.7
    if status == VerificationStatus.FAIL:
        base = 0.85
    elif status == VerificationStatus.REVIEW_REQUIRED:
        base = 0.5
    elif status == VerificationStatus.NOT_APPLICABLE:
        base = 0.95
    bonus = {
        EvidenceQuality.DIRECT: 0.05,
        EvidenceQuality.SUPPORTING: 0.02,
        EvidenceQuality.INDIRECT: -0.02,
        EvidenceQuality.CONFLICTING: -0.10,
        EvidenceQuality.MISSING: -0.20,
    }[eq]
    return round(max(0.0, min(1.0, base + bonus)), 2)


def _review_question_for_reason(reason: ReviewReason, item: ChecklistItem) -> str:
    item_title = item.title
    mapping = {
        ReviewReason.MISSING_EVIDENCE: f"{item_title} 所需的文档片段未能识别。请确认相关章节是否在文档中。",
        ReviewReason.EXTRACTION_FAILED: f"{item_title} 所需字段未能从 PDF 抽取。请提供原文片段以供人工标注。",
        ReviewReason.TABLE_EXTRACTION_FAILED: f"{item_title} 依赖报价表/参数表，未能解析出结构化表格。请提供 CSV/XLSX 或人工填写数据。",
        ReviewReason.RETRIEVAL_FAILED: f"{item_title} 检索未命中相关章节。请确认关键词是否准确。",
        ReviewReason.REQUIREMENT_UNRESOLVED: f"{item_title} 招标文件中阈值/标准未明确。请与招标方确认。",
        ReviewReason.RULE_UNRESOLVED: f"{item_title} 当前 Rule Engine 无法判定。请澄清规则定义。",
        ReviewReason.EVIDENCE_CONFLICT: f"{item_title} 招标与投标存在冲突。请人工仲裁哪份为准。",
        ReviewReason.EXTERNAL_DATA_REQUIRED: f"{item_title} 需要查询外部系统（军队采购失信名单/政府采购目录/产品官网）。请人工查询后回填。",
        ReviewReason.HUMAN_PROCESS_REQUIRED: f"{item_title} 属于企业流程事项，请按 SOP 处理并留痕。",
        ReviewReason.STRATEGY_REQUIRED: f"{item_title} 涉及商业策略，请业务负责人决策。",
    }
    return mapping.get(reason, item.review_question or f"请人工复核 {item_title}")


def _recommended_action_for(reason: ReviewReason, item: ChecklistItem) -> str:
    return item.recommended_action or {
        ReviewReason.MISSING_EVIDENCE: "在源 PDF 上人工标注关键字段后重跑",
        ReviewReason.EXTRACTION_FAILED: "修正抽取规则或人工填入结构化字段",
        ReviewReason.TABLE_EXTRACTION_FAILED: "提供 CSV/XLSX 或人工填表",
        ReviewReason.RETRIEVAL_FAILED: "补充关键词/索引后重跑",
        ReviewReason.REQUIREMENT_UNRESOLVED: "与招标方确认阈值/标准",
        ReviewReason.RULE_UNRESOLVED: "澄清规则定义",
        ReviewReason.EVIDENCE_CONFLICT: "在 UI 中查看证据冲突，人工裁决",
        ReviewReason.EXTERNAL_DATA_REQUIRED: "查询外部系统后将结果填入 facts",
        ReviewReason.HUMAN_PROCESS_REQUIRED: "在 SOP 系统中勾选/留痕",
        ReviewReason.STRATEGY_REQUIRED: "在业务决策会上确定",
    }.get(reason, "请人工处理")


def _is_human_only(item: ChecklistItem) -> bool:
    return (
        item.review_type in (ReviewType.PROCESS_HUMAN, ReviewType.STRATEGY_HUMAN, ReviewType.EXTERNAL_DATA)
        or item.verification_method in (VerificationMethod.HUMAN_REVIEW, VerificationMethod.HUMAN)
    )


def _run_llm_verifier(ctx: VerifyContext, item: ChecklistItem, evidence: list[Evidence]) -> dict[str, Any] | None:
    if not ctx.llm.configured:
        return None
    try:
        prompt_path = ctx.prompt_path or os.path.join("prompts", "verifier.txt")
        with open(prompt_path, "r", encoding="utf-8") as fh:
            system = fh.read()
    except OSError:
        return None
    user_payload = {
        "check": item.model_dump(mode="json"),
        "evidence": [e.model_dump(mode="json") for e in evidence],
        "facts": ctx.facts,
    }
    try:
        return ctx.llm.complete_json(system, json.dumps(user_payload, ensure_ascii=False))
    except LLMUnavailable:
        return None


# ---------------------------------------------------------------------------
# Requirement Coverage Matrix (spec §十六)
# ---------------------------------------------------------------------------


def _build_coverage(
    item: ChecklistItem,
    evidence_by_req: dict[str, list[Evidence]],
    rule: RuleResult | None,
    eq: EvidenceQuality,
) -> list[RequirementCoverage]:
    """One row per atomic requirement."""

    rows: list[RequirementCoverage] = []
    by_req = evidence_by_req or {r.requirement_id: [] for r in item.atomic_requirements}
    for req in item.atomic_requirements:
        evs = by_req.get(req.requirement_id, [])
        tender_ev = next((e for e in evs if (e.doc_id or "") == "tender"), None)
        bid_ev = next((e for e in evs if (e.doc_id or "") == "bid"), None)
        cov = "FULL" if (tender_ev or bid_ev) else "MISSING"
        if tender_ev and bid_ev:
            cov = "FULL"
        elif tender_ev or bid_ev:
            cov = "PARTIAL"
        # Decision per row
        decision = "REVIEW_REQUIRED"
        if rule and rule.passed is True:
            decision = "PASS"
        elif rule and rule.passed is False:
            decision = "FAIL"
        elif rule is None:
            decision = "REVIEW_REQUIRED"
        if eq == EvidenceQuality.CONFLICTING:
            decision = "REVIEW_REQUIRED"
        rows.append(RequirementCoverage(
            requirement_id=req.requirement_id,
            requirement=req.description,
            verification=req.verification,
            tender_evidence=tender_ev,
            bid_evidence=bid_ev,
            coverage=cov,
            decision=decision,
            reason=rule.reason if rule else "",
            rule_trace=rule.to_dict() if rule else {},
        ))
    return rows


def verify_item(item: ChecklistItem, ctx: VerifyContext) -> VerificationResult:
    """Verify a single checklist item (spec §七 / §八 / §十一)."""

    check_run_id = f"{ctx.audit_id}-{item.check_id}" if ctx.audit_id else item.check_id

    if _is_human_only(item):
        reason_enum = {
            ReviewType.PROCESS_HUMAN: ReviewReason.HUMAN_PROCESS_REQUIRED,
            ReviewType.STRATEGY_HUMAN: ReviewReason.STRATEGY_REQUIRED,
            ReviewType.EXTERNAL_DATA: ReviewReason.EXTERNAL_DATA_REQUIRED,
        }.get(item.review_type, ReviewReason.HUMAN_PROCESS_REQUIRED)
        return VerificationResult(
            check_run_id=check_run_id,
            check_id=item.check_id,
            title=item.title,
            category=item.category,
            severity=item.severity,
            review_type=item.review_type,
            status=VerificationStatus.REVIEW_REQUIRED,
            method=item.verification_method,
            reason=f"{reason_enum.value}: 需 {'人工/外部数据' if item.review_type != ReviewType.STRATEGY_HUMAN else '业务决策'} 处理。",
            evidence=[],
            evidence_quality=EvidenceQuality.MISSING,
            rule_trace={"review_type": item.review_type.value},
            rule_result={},
            confidence=0.0,
            review_reason=reason_enum,
            review_question=item.review_question or _review_question_for_reason(reason_enum, item),
            recommended_action=item.recommended_action or _recommended_action_for(reason_enum, item),
            needs_human_review=True,
        )

    # ---- Spec §八: precondition check ----
    pre_ok, pre_failed = _check_preconditions(item, ctx.facts)
    if not pre_ok:
        return VerificationResult(
            check_run_id=check_run_id,
            check_id=item.check_id,
            title=item.title,
            category=item.category,
            severity=item.severity,
            review_type=item.review_type,
            status=VerificationStatus.REVIEW_REQUIRED,
            method=item.verification_method,
            reason=f"precondition(s) failed: {pre_failed}",
            evidence=[],
            evidence_quality=EvidenceQuality.MISSING,
            rule_trace={"preconditions_failed": pre_failed},
            rule_result={},
            confidence=0.0,
            review_reason=ReviewReason.MISSING_EVIDENCE,
            review_question=_review_question_for_reason(ReviewReason.MISSING_EVIDENCE, item),
            recommended_action=_recommended_action_for(ReviewReason.MISSING_EVIDENCE, item),
            needs_human_review=True,
        )

    # ---- retrieve evidence ----
    evidence = retrieve(_query_for(item), ctx.chunks, top_k=5, doc_filter=_doc_filter_for(item))

    # Bind each evidence to the most likely atomic requirement id (rough heuristic by token overlap)
    evidence_by_req: dict[str, list[Evidence]] = {r.requirement_id: [] for r in item.atomic_requirements}
    for e in evidence:
        if not item.atomic_requirements:
            break
        # pick first requirement whose description shares a token with the quote
        best = item.atomic_requirements[0].requirement_id
        best_score = 0
        for r in item.atomic_requirements:
            tokens = set(r.description)
            score = sum(1 for tok in tokens if tok and tok in e.quote)
            if score > best_score:
                best_score = score
                best = r.requirement_id
        evidence_by_req.setdefault(best, []).append(e)

    # ---- rule ----
    rule: RuleResult | None = None
    if item.rule:
        rule = run_rule(item.rule, ctx.facts)

    status = VerificationStatus.REVIEW_REQUIRED
    reason = ""
    review_q: list[str] = []
    review_reason: ReviewReason | None = None
    rule_trace: dict[str, Any] = rule.to_dict() if rule else {}
    operator = (item.rule or {}).get("operator") if item.rule else None
    is_hard_rule = operator in _HARD_RULES_NEVER_OVERRIDDEN

    if item.verification_method in (VerificationMethod.RULE, VerificationMethod.DETERMINISTIC):
        if rule is None:
            status = VerificationStatus.REVIEW_REQUIRED
            reason = "rule indeterminate"
            review_reason = ReviewReason.RULE_UNRESOLVED
        elif rule.passed is True:
            status = VerificationStatus.PASS
            reason = f"rule passed: {rule.reason}"
        elif rule.passed is False:
            status = VerificationStatus.FAIL
            reason = f"rule failed: {rule.reason}"
        else:
            status = VerificationStatus.REVIEW_REQUIRED
            reason = "rule produced no decision"
            review_reason = ReviewReason.AMBIGUOUS_RULE if False else ReviewReason.RULE_UNRESOLVED
    elif item.verification_method in (VerificationMethod.HYBRID, VerificationMethod.HYBRID_ALIAS):
        if rule and rule.passed is True:
            status = VerificationStatus.PASS
            reason = f"hybrid rule passed: {rule.reason}"
        elif rule and rule.passed is False:
            status = VerificationStatus.FAIL
            reason = f"hybrid rule failed: {rule.reason}"
        else:
            llm_resp = _run_llm_verifier(ctx, item, evidence)
            if llm_resp:
                status = VerificationStatus(llm_resp.get("status", "REVIEW_REQUIRED"))
                reason = llm_resp.get("reason", "")
                review_q = llm_resp.get("review_questions", []) or []
                review_reason = ReviewReason.MISSING_EVIDENCE
            else:
                status = VerificationStatus.REVIEW_REQUIRED
                reason = "rule indeterminate and no LLM available"
                review_reason = ReviewReason.MISSING_EVIDENCE
    elif item.verification_method in (VerificationMethod.LLM, VerificationMethod.SEMANTIC):
        llm_resp = _run_llm_verifier(ctx, item, evidence)
        if llm_resp:
            status = VerificationStatus(llm_resp.get("status", "REVIEW_REQUIRED"))
            reason = llm_resp.get("reason", "")
            review_q = llm_resp.get("review_questions", []) or []
            review_reason = ReviewReason.MISSING_EVIDENCE
        else:
            status = VerificationStatus.REVIEW_REQUIRED
            reason = "LLM verifier not available; manual review required"
            review_reason = ReviewReason.MISSING_EVIDENCE

    eq = _aggregate_evidence_quality(evidence)
    # Spec §七: CRITICAL/HIGH need DIRECT (or SUPPORTING) evidence to auto-PASS.
    if (
        status == VerificationStatus.PASS
        and not is_hard_rule
        and item.severity.value in ("CRITICAL", "HIGH")
        and eq not in (EvidenceQuality.DIRECT, EvidenceQuality.SUPPORTING)
    ):
        status = VerificationStatus.REVIEW_REQUIRED
        reason = f"no DIRECT/SUPPORTING evidence (got {eq.value}), downgrade to REVIEW_REQUIRED"
        review_reason = ReviewReason.MISSING_EVIDENCE

    # Hard rules are authoritative.
    if is_hard_rule and rule is not None and rule.passed is True and status == VerificationStatus.REVIEW_REQUIRED:
        status = VerificationStatus.PASS
        reason = f"hard rule passed: {rule.reason}"
        review_reason = None

    # CONFLICTING evidence always → REVIEW_REQUIRED
    if eq == EvidenceQuality.CONFLICTING and status in (VerificationStatus.PASS, VerificationStatus.FAIL):
        status = VerificationStatus.REVIEW_REQUIRED
        reason = "conflicting evidence across documents, downgrade to REVIEW_REQUIRED"
        review_reason = ReviewReason.EVIDENCE_CONFLICT

    needs_human = status in (VerificationStatus.REVIEW_REQUIRED, VerificationStatus.NOT_APPLICABLE)

    # Requirement coverage matrix
    coverage = _build_coverage(item, evidence_by_req, rule, eq)

    return VerificationResult(
        check_run_id=check_run_id,
        check_id=item.check_id,
        title=item.title,
        category=item.category,
        severity=item.severity,
        review_type=item.review_type,
        status=status,
        method=item.verification_method,
        reason=reason,
        evidence=evidence,
        evidence_quality=eq,
        rule_trace=rule_trace,
        rule_result=rule_trace,
        confidence=_confidence(status, rule.passed if rule else None, eq),
        review_questions=review_q,
        review_reason=review_reason,
        review_question=_review_question_for_reason(review_reason, item) if review_reason else (review_q[0] if review_q else (f"请人工复核：{item.title}" if needs_human else None)),
        recommended_action=_recommended_action_for(review_reason, item) if review_reason else (item.recommended_action if needs_human else None),
        needs_human_review=needs_human,
        requirement_coverage=coverage,
        classification_reason=item.classification_reason,
    )


def verify_all(items: list[ChecklistItem], chunks: list[DocumentChunk], audit_id: str = "") -> tuple[list[VerificationResult], dict[str, Any]]:
    facts = extract_facts(chunks)
    llm = LLMClient()
    ctx = VerifyContext(chunks=chunks, facts=facts, llm=llm, audit_id=audit_id)
    results = [verify_item(it, ctx) for it in items]
    return results, facts