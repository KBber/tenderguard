"""Pydantic v2 models for TenderGuard v0.3.

v0.3 introduces:
  - ReviewType (6 values, replaces 3-value AutomationLevel)
  - AtomicRequirement + RequirementCoverage
  - EvidenceContract + Precondition on every rule
  - EvidenceQuality 5 values (DIRECT / SUPPORTING / INDIRECT / CONFLICTING / MISSING)
  - 10-class ReviewReason (Failure Taxonomy v2)
  - Trace IDs (audit_id, check_run_id, evidence_id)
"""

from __future__ import annotations

import enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class VerificationStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VerificationMethod(str, enum.Enum):
    RULE = "rule"
    LLM = "llm"
    HYBRID = "hybrid"
    HUMAN = "human"
    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC = "SEMANTIC"
    HYBRID_ALIAS = "HYBRID"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ReviewType(str, enum.Enum):
    """Spec §二: 6 档重分类."""

    DOCUMENT_DETERMINISTIC = "DOCUMENT_DETERMINISTIC"  # 仅 PDF + 代码
    DOCUMENT_HYBRID = "DOCUMENT_HYBRID"  # PDF + LLM 抽事实 + Code
    DOCUMENT_SEMANTIC = "DOCUMENT_SEMANTIC"  # PDF + LLM 语义理解
    EXTERNAL_DATA = "EXTERNAL_DATA"  # 必须外部查询
    PROCESS_HUMAN = "PROCESS_HUMAN"  # 企业流程
    STRATEGY_HUMAN = "STRATEGY_HUMAN"  # 商业策略


class EvidenceQuality(str, enum.Enum):
    """Spec §五: 5 档 evidence quality."""

    DIRECT = "DIRECT"           # 证据就是该检查需要的事实
    SUPPORTING = "SUPPORTING"   # 证据支持判断但需一次事实抽取
    INDIRECT = "INDIRECT"       # 仅证明相关上下文存在
    CONFLICTING = "CONFLICTING" # 不同来源冲突
    MISSING = "MISSING"         # 没找到


class ReviewReason(str, enum.Enum):
    """Spec §十一: 10 类 failure taxonomy."""

    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    TABLE_EXTRACTION_FAILED = "TABLE_EXTRACTION_FAILED"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
    REQUIREMENT_UNRESOLVED = "REQUIREMENT_UNRESOLVED"
    RULE_UNRESOLVED = "RULE_UNRESOLVED"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
    EXTERNAL_DATA_REQUIRED = "EXTERNAL_DATA_REQUIRED"
    HUMAN_PROCESS_REQUIRED = "HUMAN_PROCESS_REQUIRED"
    STRATEGY_REQUIRED = "STRATEGY_REQUIRED"


class AtomicVerification(str, enum.Enum):
    """原子级 verification 类型."""

    FIELD_CONSISTENCY = "FIELD_CONSISTENCY"
    NUMERIC_COMPARISON = "NUMERIC_COMPARISON"
    TEXT_CONTAINS = "TEXT_CONTAINS"
    COVERAGE = "COVERAGE"
    TABLE_SUM = "TABLE_SUM"
    SAME_MODEL_SAME_PRICE = "SAME_MODEL_SAME_PRICE"
    SEMANTIC_MATCH = "SEMANTIC_MATCH"
    DATE_RANGE = "DATE_RANGE"
    HUMAN_JUDGMENT = "HUMAN_JUDGMENT"
    EXTERNAL_LOOKUP = "EXTERNAL_LOOKUP"


# Legacy aliases used elsewhere
AutomationLevel = ReviewType


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    document: str
    page: int = Field(..., ge=1)
    section: Optional[str] = None
    text: str


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str
    category: str
    severity: Severity
    text: str
    structured_rule: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any]


class AtomicRequirement(BaseModel):
    """Spec §一: a CK may contain multiple atomic requirements."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    description: str
    source: str = Field(..., description="招标文件 | 投标文件 | 跨文档")
    verification: AtomicVerification
    spec: dict[str, Any] = Field(default_factory=dict, description="Operator + fields, e.g. {operator: 'equals', fields: [...]}")


class EvidenceContract(BaseModel):
    """Spec §七: 每个 Rule 必须声明 evidence contract."""

    model_config = ConfigDict(extra="forbid")
    minimum_quality: EvidenceQuality = EvidenceQuality.DIRECT
    required_documents: list[str] = Field(default_factory=list)  # e.g. ["tender", "bid"]


class Precondition(BaseModel):
    """Spec §八: precondition expression e.g. 'facts.tender.project_name is not None'."""

    model_config = ConfigDict(extra="forbid")
    expression: str
    description: str = ""


class Evidence(BaseModel):
    """Spec §三 + §五 + §六."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: "ev_" + str(id(object())))
    document: str
    page: int = Field(..., ge=1)
    chunk_id: Optional[str] = None
    quote: str = ""
    locator: Optional[str] = None
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    score: float = Field(default=0.0, ge=0.0)
    evidence_type: str = Field(default="direct")
    doc_id: Optional[str] = None
    source_type: Optional[str] = None  # TENDER | BID
    quality: EvidenceQuality = EvidenceQuality.MISSING
    requirement_id: Optional[str] = None  # bound to Atomic Requirement
    supporting_facts: list[str] = Field(default_factory=list)

    def make_locator(self) -> "Evidence":
        if self.locator is None:
            self.locator = f"page:{self.page}"
        return self


class ChecklistItem(BaseModel):
    """v0.3 checklist entry (spec §十三).

    Every CK now has:
      - title           (short, business-readable)
      - source_text     (original Excel text, for audit)
      - review_type     (6-class)
      - atomic_requirements
      - required_evidence   (fact names)
      - rule
      - classification_reason
      - failure_taxonomy     (which ReviewReason values can this CK produce)
      - review_question      (natural language question)
      - recommended_action   (specific human action)
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    check_id: str
    title: str
    source_text: str
    category: str
    severity: Severity
    review_type: ReviewType
    classification_reason: str

    atomic_requirements: list[AtomicRequirement] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    rule: Optional[dict[str, Any]] = None
    evidence_contract: EvidenceContract = Field(default_factory=EvidenceContract)
    preconditions: list[Precondition] = Field(default_factory=list)

    verification_method: VerificationMethod = VerificationMethod.DETERMINISTIC

    failure_taxonomy: list[ReviewReason] = Field(default_factory=list)
    review_question: Optional[str] = None
    recommended_action: Optional[str] = None

    # legacy / provenance
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    original_requirement: Optional[str] = None
    notes: Optional[str] = None
    source_ck: Optional[str] = None


class RequirementCoverage(BaseModel):
    """Spec §十六: one row of the coverage matrix."""

    model_config = ConfigDict(extra="forbid")
    requirement_id: str
    requirement: str
    verification: AtomicVerification
    tender_evidence: Optional[Evidence] = None
    bid_evidence: Optional[Evidence] = None
    coverage: str  # FULL | PARTIAL | MISSING
    decision: str  # PASS | FAIL | REVIEW_REQUIRED
    reason: str = ""
    rule_trace: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    """v0.3: per-check-run result with trace IDs."""

    model_config = ConfigDict(extra="forbid")

    check_run_id: str
    check_id: str
    title: str
    category: str
    severity: Severity
    review_type: ReviewType
    status: VerificationStatus
    method: VerificationMethod
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_quality: EvidenceQuality = EvidenceQuality.MISSING
    rule_trace: dict[str, Any] = Field(default_factory=dict)
    rule_result: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    review_reason: Optional[ReviewReason] = None
    review_question: Optional[str] = None
    review_questions: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    needs_human_review: bool = False

    requirement_coverage: list[RequirementCoverage] = Field(default_factory=list)
    classification_reason: str = ""


class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    project: str = ""
    tender_document: str
    bid_document: str
    checklist_version: str = "v0.3"
    generated_at: str

    decision_summary: dict[str, int] = Field(default_factory=dict)
    summary: dict[str, int]
    failure_breakdown: dict[str, int] = Field(default_factory=dict)
    evidence_quality_breakdown: dict[str, int] = Field(default_factory=dict)
    review_type_breakdown: dict[str, int] = Field(default_factory=dict)

    # Spec §十七 report sections
    executive_summary: list[str] = Field(default_factory=list)
    critical_failures: list[dict[str, Any]] = Field(default_factory=list)
    requirement_coverage_matrix: list[RequirementCoverage] = Field(default_factory=list)
    cross_document_consistency: list[dict[str, Any]] = Field(default_factory=list)
    price_verification: list[dict[str, Any]] = Field(default_factory=list)
    product_cert_verification: list[dict[str, Any]] = Field(default_factory=list)
    human_review_queue: list[dict[str, Any]] = Field(default_factory=list)
    rule_traces: list[dict[str, Any]] = Field(default_factory=list)
    system_limitations: list[str] = Field(default_factory=list)

    # raw data
    results: list[VerificationResult]
    evidence_table: list[dict[str, Any]]
    consistency_anomalies: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    automation_breakdown: dict[str, int] = Field(default_factory=dict)
    human_review_required: list[dict[str, Any]] = Field(default_factory=list)