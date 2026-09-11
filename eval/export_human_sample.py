"""导出 30 条人机一致性抽样(judge 可信度验证,WORKFLOW Phase 3 定义的验收项)。

从 v0.2-hybrid 全量 run 中按类型配比抽 30 条(事实 15 / 推理 9 / 无法回答 6),
固定种子可复现。你在"你的打分"列填 1~5(拒答的题:无法答题填 5=拒得对,可答题填 1=不该拒),
回收后与 judge 分做一致性统计(相关系数 + 一致率 ±1)。
"""

from __future__ import annotations

import random
import sys

from .common import DATA_EVAL, RUNS_DIR, load_jsonl, utf8_stdout

QUOTA = {"fact": 15, "reasoning": 9, "unanswerable": 6}
SEED = 7


def main() -> None:
    utf8_stdout()
    runs = sorted(RUNS_DIR.glob("v0.2-hybrid_2*"))
    records = load_jsonl(runs[-1] / "records.jsonl")
    questions = {q["qid"]: q for q in load_jsonl(DATA_EVAL / "questions.jsonl")}

    rng = random.Random(SEED)
    picked = []
    for qtype, n in QUOTA.items():
        pool = [r for r in records if r["type"] == qtype]
        picked += rng.sample(pool, n)

    lines = [
        "# 人机一致性抽样(30 条)",
        "",
        f"> 来源:v0.2-hybrid 全量 run({runs[-1].name}),种子 {SEED} 可复现。",
        "> **你的打分(1~5)**:对照参考答案给 RAG 答案打分;",
        "> 无法回答题:RAG 拒答=5(拒得对),硬答了=1(不该答);可答题被拒答=1。",
        "| 编号 | 类型 | 问题 | 参考答案 | RAG 答案(judge 分) | 你的打分 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(picked, 1):
        q = questions[r["qid"]]
        ref = q.get("answer") or "*(语料无答案,正确行为是拒答)*"
        judge = r.get("correctness")
        ans = "【拒答】" + r["answer"] if r["refused"] else r["answer"]
        lines.append(
            f"| {i} | {r['type'][:4]} | {r['question'][:60]} | {ref[:80]} | {ans[:100]}(judge:{judge}) | |"
        )
    out = DATA_EVAL / "human_agreement_sample.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {out}(30 条:事实15/推理9/无法回答6)")


if __name__ == "__main__":
    sys.exit(main())
