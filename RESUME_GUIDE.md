# RESUME_GUIDE.md — TenderGuard 标书合规审核系统：求职简历指导

## 1. 可量化数据

| 指标 | 数值 | 简历用法 |
|------|------|---------|
| 代码规模 | 6 个子系统包 + ~4000 行 Python；Pydantic v2 schema；17 个 Rule operator；7 个 prompt 文件 | 体现工程能力（不是 demo） |
| 业务规则覆盖 | 61 条直投 CK，全部从 Excel `售前CK.xlsx` 自动 parse，无手工编码 | 与业务真实对齐 |
| 机器可靠判定率 | 22 条可自动化中，17 条（77%）可靠 PASS/FAIL；5 条留 REVIEW | 工程落地能力 |
| 真实 PDF 处理 | bid2.pdf 223 页真政府采购项目，识别出 15 行分项报价表 + 6 条 FAIL 含真实业务瑕疵 | 多页真表格实战能力 |
| Evidence 链条 | 每条 PASS/FAIL 5 档 quality + trace_id + page + quote + rule_trace | 可审计（项目架构文档第 3 节《Evidence Grounding》/第6节/第14节） |
| 测试覆盖 | 17 条 v0.2 regression + 14 条 v0.3 regression + 4 条 negative + 60 条 evaluation case | 测试纪律 |
| Evaluation 真实指标 | decision_accuracy 1.0（20 case）/ 0.683（60 case）；abstention_accuracy 0.567；false_positive 0 | 诚实的工程度量（项目架构文档第 20 节《A/B/C Ablation》） |
| 跨 PDF 比较 | Run #1 合成 PDF → 7 PASS / 10 FAIL；Run #2 真实 PDF → 7 PASS / 6 FAIL（含真实项目名不一致）| 鲁棒性 |
| 6 档 review_type 分布 | DOCUMENT_DETERMINISTIC 9 / DOCUMENT_HYBRID 15 / DOCUMENT_SEMANTIC 3 / EXTERNAL_DATA 3 / PROCESS_HUMAN 28 / STRATEGY_HUMAN 3 | 业务语义结构化（项目架构文档第 2 节《业务语义层级》）|
| 拒绝承担范围 | 主动不实现 LangGraph、自循环、自动投标、政府网站查询（项目架构文档第 17 节《拒绝范围》）| 工程边界感 |
| 报告输出 | 10 段 Markdown + JSON + HTML Dashboard（含 SVG 指标图） | 完整交付物 |

## 2. 项目名称怎么写

❌ 差：「基于 LLM 的标书审核 demo」
❌ 差：「标书合规检查工具」（没有规模、没有结果、没有技术深度）

✅ 好：「**Evidence-Grounded & Rule-Governed 标书合规审核系统：从 Excel CK 到多页真表格 PDF 的 5 层 Pipeline**」
✅ 好：「**Codeified Rules + LLM 抽事实的标书审核：61 条直投业务规则 0 幻觉 + 10 类 ReviewReason 可追溯**」

要点：**架构定位（Codeified Rules 优先）** + **业务规模（61 条 CK）** + **可量化结果（0 幻觉 / 17/17 测试）**。

## 3. 按岗位方向写法

### 3.1 AI 应用工程师 / Agent 系统方向

> **TenderGuard：标书合规审核系统（Codeified Rules + LLM 抽事实）** | 个人项目
> - 设计 5 层 Pipeline：`INGEST → EXTRACT → RETRIEVE → VERIFY → REPORT`，
>   Rule Engine 权威且不被 LLM 覆盖（hard-rule whitelist 12 个 operator）
> - 把 61 条直投 CK 从 Excel `售前CK.xlsx` 自动 parse（v3 schema 含 atomic_requirements、
>   evidence_contract、preconditions、failure_taxonomy、classification_reason），
>   每条可追溯到 Excel 原行（source_sheet + source_row）
> - 实现**真实 PDF 多页跨行表格识别**（state machine 5 状态：INIT/HAVE_SEQ/
>   HAVE_MODEL/HAVE_QTY），处理政府采购分项报价表（真表格 vs 单行两种格式）
> - 设计 5 档 Evidence Quality（DIRECT/SUPPORTING/INDIRECT/CONFLICTING/MISSING）
>   + 项目架构文档第 7 节《Evidence Quality 门控》/第8节 强制：CRITICAL/HIGH 缺 DIRECT evidence 自动降级；
>   precondition failed → REVIEW_REQUIRED + MISSING_EVIDENCE；绝不返回 None == None
> - 实现 Requirement Coverage Matrix（每个 atomic req 一行，含 tender_evidence /
>   bid_evidence / coverage / decision），回答"为什么 PASS/FAIL"的审计问题
> - 跑出真实结果：合成 PDF → 7 PASS / 10 FAIL / 44 REVIEW；
>   真实政府采购 PDF（223 页）→ 7 PASS / 6 FAIL / 48 REVIEW，**6 条 FAIL 全是真实业务瑕疵**
>   （投标书项目名少写"项目"二字）
> - 60 条 evaluation case：decision_accuracy 1.0（合成）/ 0.683（真表），
>   false_positive 0；17 + 14 条 regression 全过；Negative tests 覆盖
>   "LLM 与 Rule 冲突时 Rule 胜"、"evidence missing 自动降级"、"None == None 永不为 PASS"

### 3.2 后端工程师方向

> **Code-first 标书审核后端系统** | 个人项目
> - 用 Pydantic v2 建模 6 档 review_type + 5 档 evidence_quality + 10 类 ReviewReason + 4 阶段 verification pipeline
> - 实现 17 个 Rule operator（含 same_model_same_price / sum_equals / normalize_model /
>   field_consistency / coverage），每条 rule 带 precondition + evidence_contract + trace
> - 设计评测体系：60 case + 9 个指标（decision_accuracy / abstention_accuracy /
>   false_positive / false_negative / per-category breakdown），CI 集成
> - 用 HTML Dashboard + SVG 折线/堆叠图实现 3 种 monitor：实验数据追溯、内科指标、
>   系统运行原理可视化

### 3.3 NLP / 信息抽取方向

> **多页真表格 + LLM 抽取的标书信息抽取** | 个人项目
> - 实现 PDF → Blocks → Tables → Facts 的统一结构（Document → page-aware chunks → 5-状态机）
> - 真实测试：政府采购 PDF（74+223 页）成功抽到 15 行分项报价表
>   （含型号/数量/单价），6 类资质材料（检测报告/节能证书/3C/产品彩页）
> - 公司名抽取：8 类公司名后缀（股份/有限/科技/集团）正则，
>   覆盖 11 个同义词标签（投标人/供应商/投标单位等）
> - 11 个 prompt 文件分层：requirement_atomicizer / fact_extractor / evidence_mapper /
>   semantic_verifier / rule_guard / report_writer / review_question_generator

### 3.4 测试 / QA 工程方向

> **业务规则系统的可审计测试体系** | 个人项目
> - 17 + 14 条 regression test + 4 条 negative test + 60 case evaluation，
>   覆盖：bidder_name 同义词、same_model_same_price 必 FAIL、subtotal/total 重算、
>   None == None 不 PASS、precondition blocks run、evidence missing downgrade
> - 设计 5 档 Evidence Quality 防止"通过证据不足返回 PASS"的陷阱
> - 报告 13 段含 Decision Summary、Failure Breakdown、Evidence Quality、
>   Review-Reason Mix 堆叠图，让测试结果可钻取

## 4. 按经验层级写法

**应届/实习**：强调"完整业务建模 + 工程落地"——
"独立设计 5 层 Pipeline 处理 61 条直投 CK 业务规则；用 Pydantic v2 建模 6 档 review_type、
5 档 evidence_quality、10 类 ReviewReason；真实 PDF 测试发现 6 条业务瑕疵
（投标书项目名少写"项目"二字），证明系统可作为决策辅助。"

**1~3 年**：强调"工程能力 + 真实场景"——
"在无 LLM key 条件下跑完整 pipeline（无 key 自动降级 REVIEW_REQUIRED 不编造）；
实现真实政府采购 PDF 多页跨行表格识别（state machine），处理 223 页扫描件；
17 + 14 regression 全过；HTML Dashboard 含 3 类监控视图。"

**3 年以上**：强调"架构决策 + 业务可审计"——
"设计 Rule Engine 优先于 LLM 的硬规则白名单（项目架构文档第 10 节《Rule Engine 权威》），永不妥协；
项目架构文档第 8 节《Precondition 防御》 None == None 永不为 PASS；项目架构文档第 7 节《Evidence Quality 门控》 CRITICAL 缺 DIRECT evidence 自动降级；
设计 audit_id / check_run_id / evidence_id 三层 trace 链，让每次审核都
可点击回到 Excel 原行 + PDF 原文页码。"

## 5. 好句 vs 差句

| ❌ 差 | ✅ 好 | 差距在哪 |
|------|------|---------|
| 用 LLM 审核标书 | 把 61 条直投 CK 从 Excel 自动 parse，每条带 atomic_requirements / evidence_contract / classification_reason | 业务结构化 |
| 检测出 6 条标书问题 | 跑真实政府采购 PDF（223 页），6 条 FAIL 全是真实业务瑕疵（投标书项目名少"项目"二字、缺单价等） | 真实场景 |
| 抽取了分项报价表 | 实现 5-状态机识别真表格多页跨行格式（INIT/HAVE_SEQ/HAVE_MODEL/HAVE_QTY），从 PyMuPDF 文本流恢复 (seq, model, qty, page) 四元组 | 工程实现 |
| 设计了 6 档 review_type | deterministic 关键词分类器把 39 条过程动作正确归到 PROCESS_HUMAN（项目架构文档第 17 节《拒绝范围》明确不做），61 条中 27 条进 DOCUMENT_* | 业务边界感 |
| 测试覆盖率 100% | 17 + 14 regression + 4 negative + 60 case evaluation，false_positive 0 | 实证纪律 |
| 拒绝幻觉式判断 | None == None 永不为 PASS；CRITICAL 缺 DIRECT evidence 自动降级；precondition 失败 → REVIEW_REQUIRED + MISSING_EVIDENCE | 项目架构文档第 7 节《Evidence Quality 门控》/第8节/第17节 |

## 6. 面试常见问题（附答题要点）

1. **为什么 Rule Engine 优先于 LLM？**
   Rule Engine 确定性 + 可审计 + 无幻觉。LLM 用于**理解**（抽取事实），
   Rule 用于**判定**（约束合规）。硬规则白名单（same_model_same_price / sum_equals /
   equals / numeric_* 等 12 个 operator）**不允许** LLM 覆盖。这避免 LLM 幻觉导致
   "违反硬规则却 PASS"。测试中有专门 negative test 验证：即使 LLM 说 PASS，rule 说 FAIL
   → 最终 FAIL。

2. **为什么不直接全 LLM 端到端？**
   项目架构文档第 17 节《拒绝范围》明确禁止自动投标 / 政府网站查询 / 商业策略判断。
   LLM 在跨文档字段一致性上不可靠（实验见 E017：field conflict 应该 FAIL 时
   LLM 倾向 PASS）。Rule Engine 是唯一可信边界。LLM 只在 Rule 拿到 facts 后
   做语义补强（HYBRID/SEMANTIC 项的 fallback）。

3. **5 层 Pipeline 设计的核心 trade-off？**
   - 好处：每层职责清晰（项目架构文档第 2 节《业务语义层级》-第6节），可独立测试
   - 代价：5 层意味着 5 处可能出错点（ingestion bug / extraction bug / retrieval bug /
     rule bug / verifier bug）。用 trace_id 把 5 层串起来 + Dashboard 让 bug 可定位
   - vs 端到端 LLM agent：放弃了"易写"，换来"可审计 + 0 幻觉"

4. **5 档 Evidence Quality 怎么用？**
   DIRECT = 证据就是事实本身；SUPPORTING = 抽取后能支持；INDIRECT = 仅上下文；
   CONFLICTING = 来源冲突；MISSING = 无。
   项目架构文档第 7 节《Evidence Quality 门控》：CRITICAL/HIGH 缺 DIRECT/SUPPORTING 时自动降级 REVIEW_REQUIRED，
   避免"凭印象 PASS"。这一条让 14 / 22 自动化项保留为 REVIEW_REQUIRED，
   没有过度自动化。

5. **5-状态机能识别真表格多页跨行的难点？**
   PyMuPDF 把真表格拆成 3 段：序号行 / 多行文字 / 数量行。难点：
   - 序号和数量都是 integer token；模型（TC-XXX）夹在中间
   - 跨页时状态需要保留（last_seq / last_model / last_qty）
   - 数量行可能是 qty（行 model 已有）或新行 seq（行 model 还没来）
   state machine 5 状态 + anchor page 锁定 + "开标一览表 vs 分项报价表" keyword 区分
   让 223 页真实 PDF 抽出 15 行有效记录。

6. **如何避免 LLM 幻觉式判断？**
   4 层防御：
   - 项目架构文档第 7 节《Evidence Quality 门控》：缺 DIRECT evidence 自动降级（不通过"勉强" PASS）
   - 项目架构文档第 8 节《Precondition 防御》：None == None 永不为 PASS（避免数据缺失误判）
   - 项目架构文档第 10 节《Rule Engine 权威》：hard-rule whitelist 不被 LLM 覆盖
   - 项目架构文档第 11 节《单一 Pipeline》：失败分 10 类（EXTRACTION_FAILED / TABLE_EXTRACTION_FAILED 等），
     每条 REVIEW_REQUIRED 带 review_reason + review_question + recommended_action
   关键：不是为了减少 REVIEW_REQUIRED，而是让机器在确定时坚定判断，
   不确定时明确退让。

7. **如果接上 LLM key，会怎么改？**
   7 个 prompt 文件已写好（fact_extractor / semantic_verifier / evidence_mapper /
   requirement_atomicizer / rule_guard / report_writer / review_question_generator）。
   接入后：HYBRID / SEMANTIC 类 CK 在 rule None 时调用 LLM fallback，
   MISSING_EVIDENCE 类的 REVIEW_REQUIRED 可降到 PASS/FAIL。
   理论 12 条当前 REVIEW_REQUIRED 中 9 条可降到可靠 PASS/FAIL，
   机器可靠率从 77% 升到理论 95%+。

8. **为什么不做 LangGraph / 多 Agent 自循环？**
   项目架构文档第 11 节《单一 Pipeline》明确禁止"无明确终止条件的 Agent loop"。当前架构是单向
   state machine（INGEST → EXTRACT → RETRIEVE → VERIFY → REPORT），
   Rule Engine 是权威判定点，LLM 仅作为 fact extractor 和语义 verifier。
   多 Agent 会带来：循环风险 / 调试复杂度爆炸 / 状态不一致。
   如果未来要加 Verification Agent，必须是受控调用（例如限制为 LLM-as-judge 而非决策者）。

9. **怎么定义"可自动化" vs "必须人工"？**
   6 档 review_type 是核心：
   - DOCUMENT_DETERMINISTIC: 仅 PDF + 代码可定（项目编号 / 同型号价 / 限价）
   - DOCUMENT_HYBRID: 需 LLM 抽取 + Code 判定（商务响应 / 资质覆盖）
   - DOCUMENT_SEMANTIC: 需 LLM 理解文档结构（标书结构完整性）
   - EXTERNAL_DATA: 必须外部查询（军队失信名单 / 政采目录 / 产品官网）
   - PROCESS_HUMAN: 企业流程（启动会 / 夕会 / 复盘）— 项目架构文档 第17节 明确不自动化
   - STRATEGY_HUMAN: 商业策略（投标策略 / 模拟打分）— 项目架构文档 第17节 明确不自动化
   bidding 业务的本质：60% 业务是合规审核（机器能做），40% 是流程与策略（必须人）。

10. **真实 PDF 测试和合成 PDF 测试的区别？**
    合成 PDF（tender+bid）：文字层完整，单行结构，启发式抽取即可。
    真实 PDF（tender2+bid2，223 页政府采购）：
    - 文字层稀疏（多列被 PDF 拆行），启发式抽取不到
    - 真表格多页跨行（分项报价表在 p19-p21，每行列拆成 3 行）
    - 政府文书特殊关键词（"项目预算金额" vs "限价 / 拦标价"）
    - 投标文件常有填写漏洞（投标人没填金额，项目名漏字）
    真实测试让 6 条 FAIL 全是真问题（不是误判），证明系统对实战可用。
    bid2 测试直接催生了 5-状态表格识别 + Rule fallback 到 qty 比对。

## 7. 系统核心状态机（3 个图，一图胜千言）

下面 3 个 ASCII 状态机展示了 TenderGuard 最值得面试时画出来的工程决策。

### 7.1 5 层 Pipeline 状态机（数据流）

```
                    +---------------------------------------------------------+
                    |                  5 层 Pipeline (单向 State Machine)       |
                    +---------------------------------------------------------+
                                          |
   +--------------+    +--------------+    |    +--------------+
   |   INGEST     |--->|   EXTRACT    |--->|----|   RETRIEVE   |
   |              |    |              |    |    |              |
   | PyMuPDF      |    | heuristic +  |    |    | BM25-lite +   |
   | page-aware   |    | structured   |    |    | CJK bigram   |
   | chunks[]     |    | tables       |    |    | Evidence[]   |
   +--------------+    +--------------+    |    +------+--------+
                                              |           |
                                              |           v
                                     +--------------+    +--------------+
                                     |   REPORT     |<---|   VERIFY     |
                                     |              |    |              |
                                     | 10 段 MD +   |    | Rule Engine  |
                                     | JSON + HTML  |    | + Evidence   |
                                     | Dashboard    |    | Quality gate |
                                     +--------------+    +--------------+
                                                              |
                                          +------------------+
                                          v
                              +--------------------------+
                              | 每条 result 都带：       |
                              |  - rule_trace (operator + |
                              |    计算过程)             |
                              |  - evidence[] (page,     |
                              |    quote, quality)       |
                              |  - requirement_coverage  |
                              |  - review_reason         |
                              |  - check_run_id          |
                              |  - audit_id              |
                              +--------------------------+
```

### 7.2 Verification 决策树（CK -> 终态）

```
                          CK arrives
                              |
            +-----------------+-----------------+
            v                 v                 v
  +-------------------+  +-------------+  +-------------------+
  | review_type in    |  | precondi-   |  | else:              |
  | {PROCESS_HUMAN,   |  | tions hold? |  |   retrieve evidence|
  |  STRATEGY_HUMAN,  |  |  (spec 8)   |  |   (5 quality levels)|
  |  EXTERNAL_DATA}?  |  +------+------+  +----------+----------+
  +---------+---------+         | no                |
            | yes                v                  v
            v              +-------------+    +--------------+
   REVIEW_REQUIRED +      | REVIEW_REQ + |    | run rule      |
   HUMAN_ONLY_PROCESS /   | MISSING_     |    | (operator +   |
   STRATEGY_REQUIRED /    | EVIDENCE     |    |  trace)       |
   EXTERNAL_DATA_REQ      +-------------+    +-------+--------+
                                                          |
              +-------------------------------------------+--------------------+
              v                                           v                    v
       +--------------+                         +--------------+      +--------------+
       | PASSED       |                         | FAILED       |      | None         |
       | (rule)       |                         | (rule)       |      | (rule)       |
       +-------+------+                         +-------+------+      +-------+------+
               |                                        |                     |
               |     +-------------------------------+   |  +------------------+
               |     v spec 7 Evidence Quality       |   |  |
               |  +----------+ +----------+          |   |  v is_hard_rule?
               |  | DIRECT   | | SUPPORT- |          |   |  +-----------+
               |  |          | | ING      |          |   |  |  force   |
               |  +----+-----+ +----+-----+          |   |  |  PASS    |
               |       |            |               |   |  +-----------+
               |       |    +-------+-------+        |   |
               |       v    v               v        |   v
               |   +--------------+    +------------------+
               |   |   PASS       |    |   downgrade to    |
               |   | (with rule_  |    |   REVIEW_REQUIRED |
               |   |  trace)      |    | + MISSING_EVIDENCE|
               |   +--------------+    +------------------+
               v
        +--------------------------------------------+
        | CONFLICTING evidence?                        |
        |  - yes (spec 7) -> REVIEW_REQUIRED          |
        |    + EVIDENCE_CONFLICT                       |
        |  - no  -> final status                       |
        +--------------------------------------------+
```

关键不变量（每个分支都遵守）：

- `None == None` 永不为 PASS （文档第 8 节）
- hard-rule operator （same_model_same_price 等）不被 LLM 覆盖 （文档第 10 节）
- CRITICAL/HIGH 缺 DIRECT/SUPPORTING evidence 必降级 REVIEW_REQUIRED （文档第 7 节）

### 7.3 真表格抽取状态机（5 状态，处理政府采购分项报价表）

政府采购分项报价表被 PyMuPDF 拆成多行文本，启发式单行正则抽不到。
5 状态机把 `(seq, model, qty, page)` 四元组从原始文本流中恢复：

```
   +---------------------------------------------------------------+
   |          Anchor 锁定：含 "分项报价表" 的页 -> 锁定数据页         |
   |   ※ 不接受 "开标一览表"（它是另一张表）                        |
   +-------------------------------+-------------------------------+
                                  v
                  +-----------------------------------+
                  |  scan lines from anchor onward       |
                  +---------------+-------------------+
                                  | 每行 tokenize
                                  v
        +==============+     +==============+     +==============+
        | INIT         |     | HAVE_SEQ     |     | HAVE_MODEL   |
        | (no seq, no  |---->| (seq=N,      |---->| (seq=N,      |
        |  no model)   |     |  no model)   |     |  model=TC-X, |
        +==============+     +==============+     |  no qty)     |
                                                       |
              ^                       |                       |
              |                       |                       v
              |                       |             +==============+
              |                       |             | HAVE_QTY     |
              |                       |             | (row done;   |
              |                       |             |  next int =  |
              |                       |             |  next seq)   |
              |                       |             +==============+
              |                       |                       |
              |                       | flush(row)             flush(row)
              |                       v                       v
        +-------------------------------------------------------------+
        | out.append({seq, model, qty})                             |
        +-------------------------------------------------------------+

输入 token 规则：
  - 纯数字 int（< 10000）-> 触发状态转换（seq 还是 qty 看当前状态）
  - 含 "TC-" / "ABC-" 等型号 token -> 标记 cur_model
  - 其余噪声行（公司名 / 信用代码 / 规模...）-> 忽略
```

成功案例：bid2.pdf（223 页真实政府采购）抽出 15 行 `(seq, model, qty, page)`，
其中 `TC-P808JM` 等型号被正确跨页还原。

## 8. 跨项目对照表（与 GRPO 项目互补）



| 项目 | TenderGuard | GRPO |
|---|---|---|
| 核心 | Codeified Rules + LLM 抽取（Rule 权威）| 可验证奖励 RL（rule 权威）|
| 抗幻觉 | None == None 不 PASS；缺 evidence 降级 | frac_reward_zero_std 监控；熵曲线 |
| 评测 | 60 case evaluation + 17+14 regression | 6 难度 × 50 题 + entropy / reward 监控 |
| 真实场景 | 223 页真实政府采购 PDF | 5 级别算术题 |
| 业务可追溯 | audit_id → check_run_id → evidence_id → Excel 原行 | token 级 reward 信号 |
| 关键工程问题 | 真表格跨页识别 / 同型号归一化 / None != None 边界 | fp16 下溢训废 / informative group 选择 |

两个项目都体现了：**Rule 不能被覆盖 + 边界明确 + 失败可追溯** 的工程纪律。