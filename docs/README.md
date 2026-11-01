# 文档导航

> 这是 rag-qa 的文档地图。先看本页，再按角色选阅读路径，不用从头翻。

## 项目一句话

基于 FastAPI 官方中文文档（122 篇 / 1,701 chunk）的 RAG 问答：混合检索定位段落，LLM 依据资料作答并逐句标注引用，资料不足时诚实拒答。

**当前版本 v0.10-top8**（200 题 × 3 轮全量）：正确性 **4.8146 ± 0.0241**、误拒 **0.00%**、
正确拒答 **100%**、安全率 **100%**、平均 **2.08s**；另在 60 题未参与调参的留出集上
**4.9444 ± 0.0098 / 误拒 0 / 正确拒答 100%**。

## 按角色阅读

| 你是 | 建议顺序 | 时间 |
|---|---|---|
| **面试官 / 评审** | 本页 → [`notes/engineering-story.md`](../notes/engineering-story.md) → [`eval/results-deepseek.md`](../eval/results-deepseek.md) 的 v0.10 与留出集章节 | 25~35 分钟 |
| **开发者（跑起来）** | [`README.md`](../README.md) 快速开始 → [`web/README.md`](../web/README.md) → [`archive/workflow-2026-09.md`](archive/workflow-2026-09.md)（历史约定，可跳过） | 15 分钟 |
| **接手维护** | 本页 → [`CHANGELOG.md`](../CHANGELOG.md) → [`archive/progress-2026-09.md`](archive/progress-2026-09.md)（2026-09 阶段存档）→ [`notes/`](../notes/) | 20 分钟 |
| **只想看结论** | [`README.md`](../README.md) 顶部数字 + 版本表 → 本文末尾「权威数据源」 | 5 分钟 |

## 文档清单

### 面向读者（现行）

| 文件 | 内容 | 状态 |
|---|---|---|
| [`README.md`](../README.md) | 项目介绍、架构、快速开始、版本表、开关说明、性能 | 现行 |
| [`CHANGELOG.md`](../CHANGELOG.md) | 版本历史：每版改了什么、指标、tag、判决 | 现行 |
| [`notes/engineering-story.md`](../notes/engineering-story.md) | 误拒 7.9% → 0 的工程复盘：度量、迭代、负结果、面试问答、局限 | 现行（推荐先读） |
| [`eval/results-deepseek.md`](../eval/results-deepseek.md) | DeepSeek 时代（v0.6~v0.10）全部跑批记录、第二 judge 复判、60 题留出集 | 现行（权威数据） |
| [`eval/results.md`](../eval/results.md) | Qwen 时代（v0.1~v0.5）结果表 | 历史，勿与 v0.6+ 直接比 |
| [`docs/chunking-analysis.md`](chunking-analysis.md) | 语料/切块/耗时分析（122 篇、1,701 chunk、单题耗时构成） | 现行（可能有小偏差） |
| [`eval/calibration.md`](../eval/calibration.md) | 拒答阈值校准曲线（结论：阈值闸门失效） | 历史结论，仍有效 |
| [`web/README.md`](../web/README.md) | Next.js 前端：SSE 流式、引用交互、本地开发 | 现行 |
| [`notes/pitfalls.md`](../notes/pitfalls.md) | 踩坑笔记（问题 → 尝试 → 结论） | 长期维护 |

### 过程记录（已收口，供追溯）

| 文件 | 内容 | 状态 |
|---|---|---|
| [`notes/false-refusal-plan.md`](../notes/false-refusal-plan.md) | 误拒 P0/P1 的计划与执行结果（A/B/C/D/E） | 已收口 |
| [`notes/overnight-plan.md`](../notes/overnight-plan.md) | 2026-10-31 夜间 A/B/C/D 的执行协议与结果 | 已收口 |

### 历史存档（docs/archive/）

| 文件 | 内容 | 状态 |
|---|---|---|
| [`archive/progress-2026-09.md`](archive/progress-2026-09.md) | 2026-09-01~09-17 的 Phase 0~6 阶段进度 | 历史存档 |
| [`archive/workflow-2026-09.md`](archive/workflow-2026-09.md) | 2026-09 的跨会话工作约定与 Phase 定义 | 历史存档 |
| [`archive/codex-review-2026-09-12.md`](archive/codex-review-2026-09-12.md) | 外部评审（Codex）待办与本机核实 | 已关闭 |

## 权威数据源

1. **原始记录**：`eval/runs/<version>_<timestamp>/records.jsonl`（逐题答案、分数、耗时、是否二次检索/改写）与 `summary.json`。records 不入库（体积大），summary 入库。
2. **汇总口径**：`eval/metrics.py::summarize`；多轮均值±标准差用 `python -m eval.aggregate <version-prefix>`。
3. **判分**：固定 `qwen3.8-27b`；第二 judge 复判用 `python -m eval.rejudge <run...> --model glm-5.3`。
4. **进入 README 的数字必须来自全量跑批**；`--limit 50` 只用于迭代止损，不写进结论。

## 维护约定

- 新版本：写 `eval/results-deepseek.md` 汇总 → 更新 `CHANGELOG.md` → 更新 README 版本表/顶部数字 → 打 annotated tag（打在代码+结果提交上，不要移动已推送的 tag）。
- 文档状态变化：在对应文件顶部加「历史存档 / 已收口」横幅，并把本页状态列改掉。
- 留出集（`data/eval/holdout.jsonl`）只用于最终确认，**不参与调参**；一旦用它调参，需重新出题。