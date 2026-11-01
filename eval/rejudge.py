"""用第二个 judge 复判已有 run 的答案，检查主 judge 的分数是否可被独立复现。

用法:
    python -m eval.rejudge eval/runs/v0.10-top8-r1_20261101_002848 --model glm-5.3

只对可答题（fact/reasoning、未拒答、原 correctness 非空）重算正确性；复用 eval.judge.correctness，
参考答案取 questions.jsonl 的 answer 字段，与原跑批口径一致。不重新生成、不写 records。
输出：逐题打印差值 ≥2 的样本 + 汇总（完全一致率、±1 一致率、Pearson、平均差）。
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

from .common import REPO_ROOT, get_llm, load_jsonl, utf8_stdout
from .judge import correctness


def pearson(xs: list[int], ys: list[int]) -> float:
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--model", default="glm-5.3")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    run_dir = args.run_dir if args.run_dir.is_absolute() else REPO_ROOT / args.run_dir
    qs = {q["qid"]: q for q in load_jsonl(REPO_ROOT / "data" / "eval" / "questions.jsonl")}
    recs = load_jsonl(run_dir / "records.jsonl")
    rows = [
        r for r in recs
        if r["type"] in ("fact", "reasoning") and not r["refused"] and r.get("correctness") is not None
    ]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{run_dir.name} | 复判 {len(rows)} 条 | judge={args.model}", flush=True)

    client, _ = get_llm()
    pairs, errors = [], 0
    for i, r in enumerate(rows, 1):
        q = qs[r["qid"]]
        try:
            score, _reason = correctness(client, args.model, q["question"], q["answer"], r["answer"])
        except Exception as e:  # 网络/解析异常：记一次失败，不编造分数
            errors += 1
            print(f"  [{i}] {r['qid']} ERROR {type(e).__name__}: {str(e)[:80]}", flush=True)
            continue
        if score == 0:
            errors += 1
            continue
        pairs.append((r["qid"], r["correctness"], score))
        if abs(score - r["correctness"]) >= 2:
            print(f"  [{i}] {r['qid']} {r['correctness']} -> {score}  {q['question'][:52]}", flush=True)

    if not pairs:
        print("没有可复判样本（全部失败）")
        return 1
    old = [a for _, a, _ in pairs]
    new = [b for _, _, b in pairs]
    diffs = [b - a for a, b in zip(old, new)]
    exact = sum(d == 0 for d in diffs)
    within1 = sum(abs(d) <= 1 for d in diffs)
    print(f"\n复判 {len(pairs)} 条（失败 {errors}）")
    print(f"完全一致 {exact}/{len(pairs)} = {exact / len(pairs):.1%} | ±1 一致 {within1}/{len(pairs)} = {within1 / len(pairs):.1%}")
    print(f"Pearson {pearson(old, new):.3f} | 主 judge 均值 {st.mean(old):.3f} | 复判均值 {st.mean(new):.3f}"
          f" | 平均差 {st.mean(diffs):+.3f}")
    print(f"差值 ≥2 的题：{sum(abs(d) >= 2 for d in diffs)} 条 | 差值 ≥3：{sum(abs(d) >= 3 for d in diffs)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())