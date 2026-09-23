# TenderGuard v0.3

Evidence-Grounded, Rule-Governed Tender Compliance System.

> **核心思想**:LLM 理解招标文件和投标文件;Retrieval 寻找证据;
> Codeified Rules 执行确定性的业务规则;Verification 综合判断;
> Human Review 处理证据不足、冲突和无法自动判断的情况。
>
> **v0.3 定位**:Business Semantics + Evidence Grounding + Rule Reliability。
> 完整规范见 [`ARCHITECTURE_v0.3.md`](ARCHITECTURE_v0.3.md),变更细节见 [`CHANGELOG.md`](CHANGELOG.md)。

`售前CK.xlsx` (`data/source/`) 是 SOURCE OF TRUTH;`直投CK` 是 v0.3 的业务范围。
所有原始 CK 条目均被保留、追溯,不擅自删除。

---

## 快速开始

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 从 Excel 一次性生成 normalized checklist
python -m tenderguard.cli parse

# 3) 对真实 PDF 跑审核
python -m tenderguard.cli review \
    --tender data/tender.pdf \
    --bid    data/bid.pdf \
    --include-facts \
    --project "项目名称"

# 4) 看报告
cat output/report.json     # 结构化
cat output/report.md       # 人类可读
```

CLI 会自动:解析 Excel → 加载 61 条 CK → 摄入 PDF → 跑验证 → 输出 `report.json` + `report.md`。

> 本仓库的 `publish/` 快照为对外发布版本,**不含** `tests/` 与 `data/source/`
> (敏感数据)。完整源码见本地工作区。

---

## v0.3 核心特性

| 维度 | v0.3 实现 |
| --- | --- |
| Review Type (6 值) | `DOCUMENT_DETERMINISTIC` / `DOCUMENT_HYBRID` / `DOCUMENT_SEMANTIC` / `EXTERNAL_DATA` / `PROCESS_HUMAN` / `STRATEGY_HUMAN` |
| Evidence Quality (5 级) | `DIRECT` / `SUPPORTING` / `INDIRECT` / `CONFLICTING` / `MISSING` |
| Failure Taxonomy (10 类) | `MISSING_EVIDENCE` / `EXTRACTION_FAILED` / `TABLE_EXTRACTION_FAILED` / `RETRIEVAL_FAILED` / `REQUIREMENT_UNRESOLVED` / `RULE_UNRESOLVED` / `EVIDENCE_CONFLICT` / `EXTERNAL_DATA_REQUIRED` / `HUMAN_PROCESS_REQUIRED` / `STRATEGY_REQUIRED` |
| Atomic Requirement | 每个 CK 拆分为 1–5 个原子要求,各自绑定 evidence + decision |
| Evidence Contract | `minimum_quality` + `required_documents` 双重门控 |
| Precondition | fact-presence 前置门 (spec §八) |
| Confidence 公式 | 含 evidence_quality bonus/penalty |
| Hard-Rule 白名单 | `same_model_same_price` / `sum_equals` / `equals` / `numeric_*` / `date_*` / `count_gte` / `required` / `exists` / `contains` / `regex` / `same_value` / `field_consistency` 等 — LLM 不可覆盖 |
| Trace | `audit_id` / `check_run_id` / `evidence_id` 三级 |

**v0.3 关键规则**(spec §七/§八):

- `None == None` 永远不产 PASS。
- CRITICAL / HIGH 缺 DIRECT 证据时降级为 REVIEW_REQUIRED。
- CONFLICTING 证据一律 REVIEW_REQUIRED。
- Rule Engine 决策与 LLM 冲突时,以 Rule Engine 为准。

---

## 工程结构

```
tenderguard/
├── app/
│   ├── ingestion/      PyMuPDF page-aware 摄入,CJK 字体
│   ├── retrieval/      BM25-lite + CJK bigram (P1: BM25 / 向量 / rerank)
│   ├── extraction/     启发式事实抽取 + Document → Blocks → Tables → Facts
│   ├── rules/          17 个确定性算子 (含 hard-rule 白名单)
│   ├── verification/   Precondition → Rule → LLM fallback → Evidence bound → Confidence
│   ├── reporting/      JSON + Markdown 报告 (audit_id / executive_summary / requirement_coverage_matrix / …)
│   ├── checklists/     excel_parser / loader / review_qa
│   └── schemas/        Pydantic v2 (ChecklistItem V3 / AtomicRequirement / EvidenceContract / Precondition / VerificationResult / AuditReport)
├── cli.py              python -m tenderguard.cli {review|parse}
├── __main__.py
config/                 checklist_schema / checklists / failure_taxonomy / severity_policy
prompts/                7 个 prompt:requirement_atomicizer / fact_extractor / evidence_mapper /
                                     semantic_verifier / rule_guard / report_writer / review_question_generator
evaluation/             cases.json + cases_v3.json (60 cases) + metrics.py + runner / runner_v3
requirements.txt
```

---

## Pipeline

```
Excel (售前CK.xlsx 直投CK sheet)
    ↓ parse_excel (deterministic keyword classifier)
ChecklistItem V3 (61 items, source_sheet/source_row preserved)
    ↓ load_checklist
INGEST   →  DocumentChunk[]   (PyMuPDF, page-aware, CJK font)
EXTRACT  →  Facts             (heuristic + structured tables)
RETRIEVE →  Evidence[]        (BM25-lite + CJK bigram, 5 quality levels)
VERIFY   →  VerificationResult[] (rule-first, evidence-bound)
    ├─ precondition check (spec §八)        — if fail → REVIEW_REQUIRED + MISSING_EVIDENCE
    ├─ run rule → RuleResult (operator + trace)
    ├─ rule decision + LLM fallback (HYBRID/SEMANTIC only)
    ├─ evidence_quality aggregation
    ├─ CRITICAL/HIGH downgrade if quality < DIRECT (spec §七)
    ├─ hard-rule whitelist (rule passes even without DIRECT)
    ├─ CONFLICTING → REVIEW_REQUIRED (spec §七)
    └─ bind each evidence to the matching AtomicRequirement (spec §六)
REPORT   →  AuditReport (10 sections, JSON + Markdown)
```

---

## Rule Engine (spec §5)

| 算子 | 说明 |
| --- | --- |
| `equals` / `not_equals` | 字段值相等 / 不等(空值/None → 不定,绝不 PASS) |
| `contains` / `not_contains` | 文本包含 |
| `regex` | 正则匹配 |
| `numeric_gt/gte/lt/lte` | 数值比较(自动处理 万/亿/元/RMB) |
| `date_before` / `date_after` | 日期比较 |
| `same_value` | 多字段等价 |
| `same_model_same_price` | 同型号必须同价(ABC-100 / ABC 100 / ABC-100(含税) / abc-100 一致归一) |
| `sum_equals` | 小计/合计重算(表抽取失败 → None,非 FAIL) |
| `count_gte` | 数量阈值 |
| `required` / `exists` | 必填 / 存在性 |
| `field_consistency` | 字段一致性 |

---

## 评估

- `evaluation/cases_v3.json` —— 60 cases (15 PASS + 15 FAIL + 10 MISSING_EVIDENCE + 5 EXTRACTION_FAILED + 5 TABLE_EXTRACTION_FAILED + 5 EVIDENCE_CONFLICT + 5 AMBIGUOUS_REQUIREMENT)。
- 新指标:`decision_accuracy`、`abstention_accuracy`、`category_breakdown`、`false_positive`、`false_negative`、`true_pass`、`true_fail`、`true_review`。
- 当前跑分:`decision_accuracy = 0.683 (41/60)`,`abstention_accuracy = 0.567 (17/30)`,剩余差距主要为 fixture 精度问题。

---

## 严格遵守的工程原则 (spec §16)

1. Python 3.11+ / Pydantic 2 ✓
2. Rule Engine 与 LLM 解耦(无 key 也能跑)
3. **LLM 判断与 Rule 冲突时,Rule Engine 优先** (spec §10)
4. **CRITICAL / HIGH 缺证据时降级 REVIEW_REQUIRED** (spec §七)
5. **无证据禁止 FAIL** (spec §七/§八)
6. 所有结论可追溯到原始 Excel 行 (`source_sheet` + `source_row`)
7. 单向 Pipeline,无 LLM-to-LLM 自循环 (spec §11)
8. v0.3 **不**做:自动投标 / 提交 / 登录政府站 / 商业策略 / 外部失信名单 (spec §十七)

---

## 当前已知限制 (P1 / P2 backlog)

1. **P1 retrieval**:当前 keyword + CJK bigram,P1 升级 BM25 / 向量 / rerank。
2. **P1 事实抽取**:LLM-backed fact extractor 暂未接入(prompts 已就绪)。
3. **P1 业务语义**:业绩门槛(年限 / 个数 / 金额)阈值需由 LLM 从 CK 文本抽取并注入到 rule。
4. **P1 CK 表外业务规则**:复杂合同条款(验收 / 付款 / 培训)需要 LLM 抽取。
5. **P1 大文件性能**:20MB+ PDF 单 chunk,P1 段落级 chunking。
6. **P1 ablation**:A / B / C ablation (spec §二十) 未实现。
7. **P2 fixture 完善**:evaluation 中与 fixture 不匹配的负样本需要细化。