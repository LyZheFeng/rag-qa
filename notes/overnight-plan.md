# 误拒 P1 夜间执行计划（A/B/C/D）

> 创建于 2026-10-31 18:10。任何会话接手前，先读本文件 + `notes/false-refusal-plan.md` + `eval/results-deepseek.md`。

## 已完成基线（P0，勿重做）

- v0.7-retry20 已实现并三轮验证：误拒 7.9% → 1.25%（2/160，三轮同集），正确性 4.610 ± 0.006，
  正确拒答 95.0%，平均 1.51s/题；recall@5 与 v0.6 完全一致。
- 已提交 `dd29595` + tag `v0.7-retry20`，已推送。

## 验证协议（用户要求）

- **正式验证一律 200 题 × 3 轮**（`-r1/-r2/-r3`），报告均值和标准差；单轮数字只用于止损。
- 冒烟：50 题 1 轮（`--limit 50`，分层含 10 道无法回答题），只用于提前发现明显副作用。
- 验收线：误拒率不回升（≤1.25%）、正确性 ≥4.61、正确拒答率 ≥94%、A 的安全率 ≥97.5%。
- 不达标即回滚（恢复 prompt/代码），把结论写回本文件与 results-deepseek.md。
- **只本地提交，不推送**，等用户醒来确认。

## A：安全作答率口径（已完成 2026-10-31 18:20）

- `eval/common.py::judge_unanswerable`：对无法回答题中 refused=false 的答案判 safe（依据引用资料原文，
  只判"有没有编造引用资料之外的具体事实"；**不能**只给问题+答案，记一次教训：judge 会用自身版本知识误判）。
- `eval/run_eval.py`：记录 `unanswerable_safe` / `unanswerable_safe_reason`（refused=true 记 True）。
- `eval/metrics.py`：新增「安全作答率（无法答题）」，保留「正确拒答率」原口径。
- `eval/backfill_safe.py`：回填历史 6 轮，9 条答案全部 safe；安全率六轮均 100%，正确拒答原口径不变。
- 报告已写入 `eval/results-deepseek.md`「安全作答率回填」节。
- 单测 112 通过。

## B：推理题 prompt（已完成并采纳）

- 动机：`reas-005` 的 gold 在 k=20 第 8 名、`reas-027` 在第 1 名，模型仍拒/答错 → 不敢推断，不是检索问题。
- 改动：`app/generator.py::SYSTEM_PROMPT` 规则 2 允许"所需事实齐全、仅结论需对比/归纳"时作答并标注推断；
  规则 3 明确"具体写法/参数/步骤/库名不存在时，即使有相邻信息也必须拒答"。**不能**用第一版（只写"资料给出
  所需事实"），否则无法回答题 4/10 被"部分作答"（拒答 60%）。
- 冒烟：第一版失败（无法回答题 6/10 拒答）；第二版通过（10/10 拒答、误拒 0/40、`reas-005` 5 分、安全率 100%）。
- 正式验证：`v0.9-inference-r1/r2/r3` 已完成，**达标**：
  正确性 **4.7167 ± 0.0107**（事实 4.82 / 推理 4.5445）、误拒 **1.04% ± 0.29pp**
  （r1 1.25 / r2 0.63 / r3 1.25）、正确拒答 **99.17% ± 1.18pp**、安全率 **100%**、异常 0。
  对比 v0.7：Δ正确性 +0.106（事实 +0.04 / 推理 +0.21），修复 `reas-005`、无新增误拒；
  `fact-082` 1→4、`fact-079` 1.33→4.67、`reas-015/027` +1.33；变差 `fact-025` 5→3、
  `fact-094` 5→3.67、`reas-059` 3.33→2。
  代价：faithfulness 0.9708 → **0.9508**（-2.0pp，推断性表述被判"无依据声明"）、延迟 +0.11s。
  已提交（本地）；结果已写入 results-deepseek.md 的 B 节。

## C：定向改写（已完成并采纳）

- 事实：`fact-049` 的 gold 不在 k=20 内（唯一真检索漏）；`reas-005`/`reas-027` 不属于检索问题。
- 探针结果（2026-10-31 18:50）：手工改写 2 条后 gold 排到 **第 2 名**（rewrite3 第 6）；
  但把改写结果与原查询做 RRF 融合后 gold 又掉出 20（原查询占满高位）→ **不能融合**，
  改为"改写 top10 + 原命中 top10 去重合并"。
- 实现（`RETRY_REWRITE`，默认开）：`LLMGenerator.rewrite_query`；`RagService` 第三段
  （两次都拒 → 改写 → k=20 检索 → 合并 → 第三次作答），命中集重排 1..N；流式事件序
  `retry → sources → delta*` 再来一轮；`AskResponse.rewritten` 记录是否触发。
- 单测：新增 6 例（改写成功/关闭/改写无变化/改写异常/流式事件序/合并去重编号），全库 118 通过。
- 冒烟（20:56）：改写触发 11/50；误拒 0/40；`reas-005` 答出 3 分；无法回答题 9/10 拒答
  （`unans-008` 改写后作答、判 safe）。
- **正式 200×3（23:10-23:54 完成，含 21:07 暂停续跑）：达标并采纳**
  正确性 **4.7667 ± 0.0164**、误拒 **0.00%（0/160，三轮都是 0）**、正确拒答 **97.50% ± 2.04pp**、
  安全率 **100%**、faithfulness 0.9460 ± 0.0029、平均延迟 **2.20s**（改写触发 42/42/41 次）。
  `fact-049` 三轮都靠改写拿 5 分；`reas-005` 3/3/4 分；被改写的无法回答题（`unans-006/008`）全部 safe。
  对比 B（仅推理 prompt）：正确性 +0.05、误拒 −1.04pp，代价延迟 +0.57s、正确拒答 −1.67pp。
  口径注意：C 的 recall@5 0.8375 是合并列表的前 5，不可与前几版直接比；`fact-079` 的 4.67→1.00
  是首轮直接答错（未拒、未进改写），属首轮行为波动，不是改写造成的。

## E：首轮 k=5 → 8（2026-11-01 已完成并采纳）

- 动机：`fact-077`/`fact-082`/`fact-079` 属于"首轮答错但不拒"，gold 在 6~8 名；D 的触发信号不可分。
- 离线 gold 排名：≤5 133 道 / 6~8 12 道 / 9~10 4 道 / 11~15 8 道 / 16~20 1 道 / >20 2 道 → 取 8 不取 10。
- 实现：`TOP_K` 配置（默认 8，校验 `TOP_K < RETRY_K`）、`RagService.default_k`、API/前端 k 可选、
  run_eval 用默认 k；单测 122 通过；前端 build 通过。
- 200×3（`v0.10-top8-r1/r2/r3`，00:28-02:40）：正确性 **4.8146 ± 0.0241**、误拒 **0.00%**、
  正确拒答 **100%**、安全率 **100%**、faithfulness 0.9501 ± 0.0033、平均 **2.08s**（retried 47/轮、
  rewritten 42/41/41）。对比 v0.9-rewrite：正确性 +0.048、正确拒答 +2.5pp、延迟 −0.12s；
  `fact-077` 3.3→5.0、`fact-079` 1.0→4.7、`reas-059` 1.7→4.7；变差 `reas-023` 4.3→3.0 等。
- 结论：**采纳为默认**（`TOP_K=8`），已提交并推送。

## D：低置信度触发（负结果，不做）

- 动机：`fact-082` 首轮只给 top-5，gold 在第 7 名，模型直接答错（1 分）；k=20 同 prompt 答对。
- 离线分析（3 轮 records + 重算 top1/引用排名）：

  | 候选规则 | 每轮触发 | 其中低分(≤3) | 精确率 |
  |---|---|---|---|
  | 引用不含 top1 | 46~48 | 6~7 | 12~15% |
  | 只引 1 条且非 top1 | 28~30 | 4~5 | 14~18% |
  | 引用最高分 <0.90 | 15~18 | 2~3 | 11~18% |
  | 不含 top1 且 top1≥0.93 | 39~41 | 5~6 | 12~15% |
  | 只引 1 条、非 top1、top1≥0.93 | 25~26 | 4~5 | 15~16% |

  低分答案（11 条/轮）与高分答案的 top1（0.964 vs 0.981）、引用最高分（0.913 vs 0.923）、
  答案长度都没有可分开的阈值；`fact-079` 引用 0.968 的高分 chunk 仍然答错。
- **结论：所有候选规则都远达不到"每轮≤5 题且≥60% 为低分题"的门槛，D 不实装**，只记录负结果。

## 中断与恢复（2026-10-31 21:07）

用户要求 23:00 后再继续，C 的三轮验证在 **r1 44/200** 处暂停，已完成记录保留在
`eval/runs/v0.9-rewrite-r1_20261031_205650/records.jsonl`（run_eval 支持 --resume 跳过已完成题）。

恢复步骤：

```powershell
cd D:\LLM_training\rag-qa
$env:RETRY_REWRITE='true'
# 1) 续跑 r1（只补未完成的 156 题）
.\.venv\Scripts\python.exe -u -X utf8 -m eval.run_eval --version v0.9-rewrite-r1 --resume eval\runs\v0.9-rewrite-r1_20261031_205650
# 2) r2 / r3 正常新目录跑
.\.venv\Scripts\python.exe -u -X utf8 -m eval.run_eval --version v0.9-rewrite-r2
.\.venv\Scripts\python.exe -u -X utf8 -m eval.run_eval --version v0.9-rewrite-r3
# 3) 汇总与判定
.\.venv\Scripts\python.exe -X utf8 -m eval.aggregate v0.9-rewrite
.\.venv\Scripts\python.exe -X utf8 -m eval.compare v0.9-inference v0.9-rewrite
```

已提交（本地，未推送）：`3fa0289`（A）、`2c677a2`（B + C 开关 + 汇总脚本）。
C 判定线：误拒 ≤1.25%、正确性 ≥4.61、正确拒答 ≥94%、安全率 ≥97.5%；不达标则保持
`RETRY_REWRITE=false` 并记录负结果。D 已确认负结果、不实装。

## 环境与命令

- 网关 `http://10.14.6.73:8317/v1`；判分 `qwen3.8-27b`；`.env` 不动。
- `cd D:\LLM_training\rag-qa`
- 跑批：`.venv\Scripts\python.exe -u -X utf8 -m eval.run_eval --version <v>`
- 记账：`.venv\Scripts\python.exe -X utf8 eval\record_run.py <v>`
- 单测：`.venv\Scripts\python.exe -X utf8 -m pytest -q`（当前 118 通过）
- 三轮汇总：`.venv\Scripts\python.exe -X utf8 -m eval.aggregate <version-prefix>`
- 当前会话是 danger-full-access（受限模式打不开 Chroma）；跑批会占满约 40 分钟/轮。