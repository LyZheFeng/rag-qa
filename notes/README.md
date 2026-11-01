# notes/ · 工作记录

这里放**过程性文档**（计划、评审、复盘、踩坑），不是"当前状态"的权威来源。
判断当前版本与指标，请看 [`CHANGELOG.md`](../CHANGELOG.md)、[`eval/results-deepseek.md`](../eval/results-deepseek.md)
和 [`README.md`](../README.md)。

## 阅读顺序

| 文件 | 内容 | 状态 |
|---|---|---|
| [`engineering-story.md`](engineering-story.md) | 误拒 7.9% → 0 的工程复盘：度量设计、四次迭代、两个负结果、面试问答、局限 | **现行，推荐先读** |
| [`pitfalls.md`](pitfalls.md) | 踩坑笔记（问题 → 尝试 → 结论），长期追加 | 长期维护 |
| [`false-refusal-plan.md`](false-refusal-plan.md) | 误拒 P0/P1 的计划与 A/B/C/D/E 执行结果 | 已收口（2026-11-01） |
| [`overnight-plan.md`](overnight-plan.md) | 2026-10-31 夜间 A/B/C/D 的执行协议、断点续跑与结果 | 已收口（2026-11-01） |
| [`codex-review-2026-09-12.md`](codex-review-2026-09-12.md) | 外部评审（Codex）待办与本机核实；其中部署相关目标已取消 | 已关闭 |

## 约定

- 计划类文档完成后在顶部标注「已收口 / 历史存档」，避免被误读为待办。
- 结论性数字只写在 `eval/results-deepseek.md` 与 `CHANGELOG.md`；notes 里引用时给出来源小节。
- 新的阶段性工作建议新建 `notes/<主题>-plan.md`，完成后同样标注状态。