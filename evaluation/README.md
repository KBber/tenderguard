# TenderGuard v0.2 Evaluation Harness

## 简介

实现 spec §十九 / §二十 要求：
- 8 类测试用例（PASS / FAIL / 抽取失败 / 证据不足 / 同型号不同价 / 表格 / 计算 / 数值约束）
- 每条用例对预期 `expected_status` 与 `expected_rule_passed` 做断言
- 指标：decision accuracy / false positive / false negative / review rate

## 运行

```bash
cd F:\AI-lea\AI-Workplace\tenderguard_v0_1
python -m evaluation.runner
```

## 指标说明

| 指标 | 含义 |
|---|---|
| `decision_accuracy` | PASS / FAIL / REVIEW_REQUIRED 整体判定正确的比例 |
| `false_positives` | 期望 PASS 但实际非 PASS 的条数 |
| `false_negatives` | 期望 FAIL 但实际非 FAIL 的条数 |
| `review_rate` | 实际 REVIEW_REQUIRED 的比例 |

## A / B / C Ablation

- A — LLM Only
- B — RAG + LLM
- C — RAG + Codeified Rules + Verification（v0.2 默认路径）

v0.2 当前实装的是 C 路径。**A 和 B 路径尚未实装**（标记 `NOT MEASURED`）。

要追加 A/B 实验，需要：
1. `evaluation/runner_ab.py` 增加 `--ablation llm | rag | codeified`
2. 跑三组并对比指标

## 已知限制

- evaluation case 都是合成文本，不含真实 PDF 噪声
- A / B 路径未实装
- 没有 LLM key 时所有路径表现相同（A=B=C，因为 fallback 都是 REVIEW_REQUIRED）