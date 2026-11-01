"""用第二个 judge 复判已有 run 的答案，检查主 judge 的分数是否可被独立复现。

用法:
    python -m eval.rejudge eval/runs/v0.10-top8-r1_xxx eval/runs/v0.10-top8-r2_xxx --model glm-5.3

只对可答题（fact/reasoning、未拒答、原 correctness 非空）重算正确性；复用 eval.judge.correctness，
参考答案取 questions.jsonl 的 answer 字段，与原跑批口径一致。不重新生成、不写 records。
judge 返回解析失败（score=0）或网络异常时按 --retries 重试，仍失败才计入失败数。

输出：每个 run 的一致率/Pearson/平均差 + 合并口径；逐题打印差值 ≥2 的样本。
"""

from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from pathlib import Path

from .common import REPO_ROOT, get_llm, load_jsonl, utf8_stdout
from .judge import correctness


def pearson(xs: list[int], ys: list[int]) -> float:
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / den if den else 0.0


def score_with_retry(client, model: str, question: str, reference: str, answer: str,
                     retries: int) -> tuple[int, str]:
    last = "parse_fail"
    for attempt in range(retries + 1):
        try:
            score, reason = correctness(client, model, question, reference, answer)
        except Exception as e:  # noqa: BLE001 —— 网络/限流：退避后重试
            last = f"{type(e).__name__}: {str(e)[:60]}"
            time.sleep(2 * (attempt + 1))
            continue
        if score != 0:
            return score, reason
        last = "parse_fail"
        time.sleep(1)
    return 0, last


def rejudge_run(run_dir: Path, qs: dict, client, model: str, retries: int,
                limit: int = 0) -> tuple[list[tuple[str, int, int]], int]:
    recs = load_jsonl(run_dir / "records.jsonl")
    rows = [
        r for r in recs
        if r["type"] in ("fact", "reasoning") and not r["refused"] and r.get("correctness") is not None
    ]
    if limit:
        rows = rows[:limit]
    pairs, errors = [], 0
    for i, r in enumerate(rows, 1):
        q = qs[r["qid"]]
        score, note = score_with_retry(client, model, q["question"], q["answer"], r["answer"], retries)
        if score == 0:
            errors += 1
            print(f"  [{i}] {r['qid']} FAILED {note}", flush=True)
            continue
        pairs.append((r["qid"], r["correctness"], score))
        if abs(score - r["correctness"]) >= 2:
            print(f"  [{i}] {r['qid']} {r['correctness']} -> {score}  {q['question'][:52]}", flush=True)
        if i % 40 == 0:
            print(f"  ... {i}/{len(rows)}", flush=True)
    return pairs, errors


def summarize(pairs: list[tuple[str, int, int]], errors: int, label: str) -> None:
    if not pairs:
        print(f"{label}: 没有有效样本（失败 {errors}）")
        return
    old = [a for _, a, _ in pairs]
    new = [b for _, _, b in pairs]
    diffs = [b - a for a, b in zip(old, new)]
    exact = sum(d == 0 for d in diffs)
    within1 = sum(abs(d) <= 1 for d in diffs)
    print(f"{label}: 有效 {len(pairs)} 条（失败 {errors}）| 完全一致 {exact}/{len(pairs)} = {exact/len(pairs):.1%}"
          f" | ±1 一致 {within1}/{len(pairs)} = {within1/len(pairs):.1%}"
          f" | Pearson {pearson(old, new):.3f}"
          f" | 主 judge {st.mean(old):.3f} vs 复判 {st.mean(new):.3f}（差 {st.mean(diffs):+.3f}）"
          f" | ≥2 分差 {sum(abs(d) >= 2 for d in diffs)} 条", flush=True)


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", type=Path, nargs="+")
    ap.add_argument("--model", default="glm-5.3")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    qs = {q["qid"]: q for q in load_jsonl(REPO_ROOT / "data" / "eval" / "questions.jsonl")}
    client, _ = get_llm()
    all_pairs: list[tuple[str, int, int]] = []
    total_errors = 0
    for rd in args.run_dirs:
        run_dir = rd if rd.is_absolute() else REPO_ROOT / rd
        print(f"\n== {run_dir.name} | judge={args.model}", flush=True)
        pairs, errors = rejudge_run(run_dir, qs, client, args.model, args.retries, args.limit)
        summarize(pairs, errors, run_dir.name)
        all_pairs += pairs
        total_errors += errors
    if len(args.run_dirs) > 1:
        print(f"\n== 合并口径（{len(args.run_dirs)} 轮）", flush=True)
        summarize(all_pairs, total_errors, "ALL")
    return 0


if __name__ == "__main__":
    sys.exit(main())