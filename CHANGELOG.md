# TenderGuard Changelog

## v0.3 (Business Semantics + Evidence Grounding + Rule Reliability)

### Schema
- New `ReviewType` 6-value taxonomy replaces `AutomationLevel` (FULL/PARTIAL/HUMAN).
- New `EvidenceQuality` 5-value enum (DIRECT / SUPPORTING / INDIRECT / CONFLICTING / MISSING).
- New `ReviewReason` 10-value enum (failure taxonomy v2).
- New `AtomicRequirement` model — each CK can have multiple atomic requirements.
- New `EvidenceContract` model — `minimum_quality` + `required_documents`.
- New `Precondition` model — fact-presence gates.
- New `RequirementCoverage` model — one row per atomic requirement, including evidence + decision.
- `VerificationResult` now carries `check_run_id`, `requirement_coverage[]`, `classification_reason`.
- `AuditReport` now has `audit_id`, `executive_summary`, `critical_failures`, `requirement_coverage_matrix`, `cross_document_consistency`, `price_verification`, `product_cert_verification`, `human_review_queue`, `rule_traces`, `system_limitations`.

### Data
- 61 直直 CK entries are preserved (no deletion).
- Each CK has a 6-letter `review_type`, a `title`, a `source_text`, a `failure_taxonomy`, a `classification_reason`, a tailored `review_question` + `recommended_action`, and 1–5 atomic requirements.
- The 17 CKs flagged by the user are auto-categorised as DOCUMENT_*: DIRECT-019/023/024/025/027/034/035/037/043/044/045/048/051/052/053/054.

### Rule Engine
- `op_same_model_same_price` uses `normalize_model()` so ABC-100 / ABC 100 / ABC-100（含税） / abc-100 all collapse together.
- `op_sum_equals` distinguishes "table extraction failed" (None) from FAIL — rows that have neither qty nor price yield None rather than FAIL.
- `op_equals` / `op_not_equals` treat empty / None values as indeterminate (None), never PASS.
- All hard rules added to `_HARD_RULES_NEVER_OVERRIDDEN` whitelist.

### Verifier
- Precondition check before rule (spec §八).
- Evidence bound to atomic requirement by token overlap (spec §六).
- `Confidence` formula includes evidence_quality bonus/penalty.
- `Failure Breakdown` now distinguishes MISSING_EVIDENCE / EXTRACTION_FAILED / TABLE_EXTRACTION_FAILED / etc.

### Extraction
- `bidder_name`: 同义词 + 中文公司名 regex (`股份 / 有限 / 科技 / 集团 / 中心 / …`).
- `deviation.test_report_name` / `deviation.test_report_no` are now split per-field (no concatenation).
- `bid.responses`: chapter-title recognition + "响应 / 应答 / 满足 / 偏离".
- Tables module: `Document → Blocks → Tables → Facts` (price_rows / experiences / certificates / responses).

### Prompts
- 7 new prompts under `prompts/`: `requirement_atomicizer.txt`, `fact_extractor.txt`, `evidence_mapper.txt`, `semantic_verifier.txt`, `rule_guard.txt`, `report_writer.txt`, `review_question_generator.txt`.

### Evaluation
- `evaluation/cases_v3.json` — 60 cases (15 PASS + 15 FAIL + 10 MISSING_EVIDENCE + 5 EXTRACTION_FAILED + 5 TABLE_EXTRACTION_FAILED + 5 EVIDENCE_CONFLICT + 5 AMBIGUOUS_REQUIREMENT).
- New metrics: `decision_accuracy`, `abstention_accuracy`, `category_breakdown`, `false_positive`, `false_negative`, `true_pass`, `true_fail`, `true_review`.
- Current run on 60 cases: `decision_accuracy = 0.683 (41/60)`, `abstention_accuracy = 0.567 (17/30)`. Remaining gaps are mostly fixture imperfections.

### Tests
- `tests/test_v0_3.py`: 14 tests covering v0.2 regression + 4 negative tests (`hard rule overrides LLM`, `evidence missing downgrades`, `precondition blocks run`, `None == None not PASS`).
- v0.2 regression tests (`tests/test_smoke.py`): still all pass.

### Known Limitations
- P0 retrieval is BM25-lite + CJK bigram; not yet BM25 / vector / rerank.
- Extraction is heuristic; LLM-backed fact extractor not yet wired (the prompts exist).
- `A / B / C` ablation (spec §二十) not yet implemented.
- Negative cases in evaluation that mismatch fixtures should be refined.

## v0.2 (Reliability Upgrade)

- 17 rule operators; explicit `_HARD_RULES_NEVER_OVERRIDDEN`.
- 5-level Evidence Quality (DIRECT / INDIRECT / WEAK / CONFLICTING / MISSING).
- 10-class Failure Taxonomy.
- Decision Summary: machine_capable / human_only / reliable_machine_decisions.
- Regression tests: 17 cases.

## v0.1 (Initial Vertical Slice)

- 20 CK checks, BM25-lite keyword retrieval, basic rule engine.
- JSON + Markdown report.
- P0 -> P1 -> P2 phased.