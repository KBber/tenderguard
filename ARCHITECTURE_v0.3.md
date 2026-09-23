# TenderGuard v0.3 Architecture

> **Positioning**: Evidence-Grounded, Rule-Governed Tender Compliance System.

## 1. Design Principles (carried from v0.2)

- LLM understands, Retrieval finds evidence, Codeified Rules enforce, Verification combines, Human reviews.
- **No** LLM-to-LLM autonomous loop.
- **No** automatic bidding, submission, government-site login, or commercial strategy judgment.
- Evidence-before-conclusion. Every PASS / FAIL must have traceable evidence or rule trace.
- Rule Engine is authoritative; LLM cannot override hard rules.

## 2. v0.3 Core Schema

The unit of execution is a **ChecklistItem V3** (see `app/schemas/models.py`):

```
ChecklistItem
├── check_id, title, source_text           # traceability
├── category, severity                     # severity (CRITICAL / HIGH / MEDIUM / LOW)
├── review_type                            # 6 values (see below)
├── classification_reason                  # why this review_type?
├── atomic_requirements: [AtomicRequirement, ...]
│   └── requirement_id, description, source, verification, spec
├── required_evidence: [fact_path, ...]    # required fact names
├── rule: dict                             # operator + parameters
├── evidence_contract: {minimum_quality, required_documents}
├── preconditions: [Precondition, ...]     # fact-presence gates
├── failure_taxonomy: [ReviewReason, ...]
├── review_question, recommended_action    # natural-language
└── source_sheet, source_row               # Excel provenance
```

## 3. Review Type Taxonomy (replaces v0.2 FULL/PARTIAL/HUMAN)

| review_type | description | examples |
|---|---|---|
| `DOCUMENT_DETERMINISTIC` | Code-only | project_id equality, same-model price, ceiling, sub-totals |
| `DOCUMENT_HYBRID` | LLM extracts facts + Code decides | commercial coverage, certificate coverage, parameter compare, experience |
| `DOCUMENT_SEMANTIC` | LLM understands + Code decides | bid structure completeness, full-document coverage, negative deviation |
| `EXTERNAL_DATA` | External system lookup | 军队失信名单, 政府采购目录, 产品官网 |
| `PROCESS_HUMAN` | Enterprise process state | 启动会, 夕会, 复盘, 打印封装, 述标, 现场投标 |
| `STRATEGY_HUMAN` | Commercial strategy | 投标策略, 销售经理报价, 模拟打分 |

## 4. Evidence Quality (5 levels)

| quality | definition |
|---|---|
| `DIRECT` | The evidence IS the fact required by the check |
| `SUPPORTING` | Evidence supports the fact after one extraction step |
| `INDIRECT` | Evidence only proves related context exists |
| `CONFLICTING` | Different sources disagree |
| `MISSING` | Not found |

CRITICAL / HIGH rules require `DIRECT` or `SUPPORTING` to auto-PASS.

## 5. Failure Taxonomy (10 reasons)

| reason | when |
|---|---|
| `MISSING_EVIDENCE` | rule known but evidence is not enough |
| `EXTRACTION_FAILED` | fact extraction broke |
| `TABLE_EXTRACTION_FAILED` | quote table did not parse |
| `RETRIEVAL_FAILED` | retrieval did not return relevant chunks |
| `REQUIREMENT_UNRESOLVED` | the CK threshold is not defined |
| `RULE_UNRESOLVED` | Rule Engine produced None |
| `EVIDENCE_CONFLICT` | sources disagree |
| `EXTERNAL_DATA_REQUIRED` | need to query external systems |
| `HUMAN_PROCESS_REQUIRED` | process action |
| `STRATEGY_REQUIRED` | commercial strategy decision |

## 6. Pipeline

```
Excel (售前CK.xlsx 直投CK sheet)
    ↓ parse_excel (deterministic keyword classifier)
ChecklistItem V3 (61 items, source_sheet/source_row preserved)
    ↓ load_checklist
INGEST  →  DocumentChunk[]  (PyMuPDF, page-aware, CJK font)
EXTRACT →  Facts  (heuristic + structured tables)
RETRIEVE →  Evidence[]  (BM25-lite + CJK bigram, 5 quality levels)
VERIFY  →  VerificationResult[]  (rule-first, evidence-bound)
    ├─ precondition check (spec §八)        — if fail → REVIEW_REQUIRED + MISSING_EVIDENCE
    ├─ run rule → RuleResult (operator + trace)
    ├─ rule decision + LLM fallback (HYBRID/SEMANTIC only)
    ├─ evidence_quality aggregation
    ├─ CRITICAL/HIGH downgrade if quality < DIRECT (spec §七)
    ├─ hard-rule whitelist (rule passes even without DIRECT)
    ├─ CONFLICTING → REVIEW_REQUIRED (spec §七)
    └─ bind each evidence to the matching AtomicRequirement (spec §六)
REPORT  →  AuditReport  (10 sections, JSON + Markdown)
```

## 7. Hard-Rule Whitelist

Operators that **cannot** be overridden by LLM:

```
same_model_same_price   sum_equals
equals / not_equals     numeric_gt / gte / lt / lte
date_before / after    count_gte
required / exists       contains / not_contains / regex
same_value             field_consistency
```

`None == None` **never** produces PASS.

## 8. Trace IDs

Every run gets `audit_id`; every check gets `check_run_id`; every evidence gets `evidence_id`.

## 9. Architecture constraint

No Lang Lang, / multi-agent loop. The pipeline is a state machine:
`INGEST → EXTRACT → RETRIEVE → VERIFY → REPORT`.