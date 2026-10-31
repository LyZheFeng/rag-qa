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

## B：推理题 prompt

- 动机：`reas-005` 的 gold 在 k=20 第 8 名、`reas-027` 在第 1 名，模型仍拒/答错 → 不敢推断，不是检索问题。
- 改动：`app/generator.py::SYSTEM_PROMPT` 增一条：资料已给出相关事实时，可据此对比/归纳并标注为推断；
  只有资料完全没覆盖才拒答。
- 冒烟 50 题（重点看无法回答题是否开始乱答）→ 通过后 200×3。
- 回滚条件：无法回答题漏拒 >3/40，或误拒率、正确性任一跌破验收线。

## C：定向改写（先探针，30 分钟）

- 事实：`fact-049` 的 gold 不在 k=20 内（唯一真检索漏）；`reas-005`/`reas-027` 不属于检索问题。
- 探针：对 fact-049 用 3 个改写（补 `x-logo` / `openapi_schema` / `custom_openapi` 等官方术语）
  各 retrieve(k=20)，看 gold 是否进入前 20。
- 探针失败 → 不做，记录负结果。
- 探针成功 → 只在「二次仍拒」后加第三段 `retry_rewrite`（配置默认关），200×3。
  注意该段会同时作用于 38~40 道无法回答题，重点看正确拒答/安全率。

## D：低置信度触发（先离线分析，不写管线代码）

- 动机：`fact-082` 首轮只给 top-5，gold 在第 7 名，模型直接答错（1 分）；k=20 同 prompt 答对。
  现有二次检索只认 refused，答错但没拒的题永远拿不到深上下文。
- 先离线：读 6 轮 records，重算 top1 分数 / 引用排名，评估候选规则精确率。
- 上线门槛：每轮触发 ≤5 题且 ≥60% 是低分题（≤3 分）；否则放弃并记录。
- 过关 → 实装触发 + 200×3。

## 环境与命令

- 网关 `http://10.14.6.73:8317/v1`；判分 `qwen3.8-27b`；`.env` 不动。
- `cd D:\LLM_training\rag-qa`
- 跑批：`.venv\Scripts\python.exe -u -X utf8 -m eval.run_eval --version <v>`
- 记账：`.venv\Scripts\python.exe -X utf8 eval\record_run.py <v>`
- 单测：`.venv\Scripts\python.exe -X utf8 -m pytest -q`（当前 109 通过）
- 当前会话是 danger-full-access（受限模式打不开 Chroma）；跑批会占满约 40 分钟/轮。