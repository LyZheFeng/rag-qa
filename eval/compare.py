"""按题对比两个候选（多轮均值），用于判断改动到底把哪些题改好/改坏。

用法:
    python -m eval.compare <base-prefix> <candidate-prefix>
例:
    python -m eval.compare v0.7-retry20 v0.9-inference

匹配规则与 eval.aggregate 一致（prefix_* 与 prefix-r*）。每题的分数取该候选各轮均值。
"""

from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

from .aggregate import find_rounds
from .common import load_jsonl, utf8_stdout


def load_rounds(prefix: str) -> list[dict[str, dict]]:
    rounds = []
    for d in find_rounds(prefix):
        recs = {r["qid"]: r for r in load_jsonl(d / "records.jsonl")}
        if recs:
            rounds.append(recs)
    return rounds


def per_question(rounds: list[dict[str, dict]]) -> dict[str, dict]:
    """题级聚合：正确性取有分轮次均值，拒答记任一轮拒过。"""
    out: dict[str, dict] = {}
    qids = set().union(*[set(r) for r in rounds]) if rounds else set()
    for qid in qids:
        rs = [r[qid] for r in rounds if qid in r]
        scores = [r["correctness"] for r in rs if r.get("correctness") is not None]
        out[qid] = {
            "type": rs[0]["type"],
            "question": rs[0]["question"],
            "score": st.mean(scores) if scores else None,
            "refused_any": any(r["refused"] for r in rs),
            "refused_all": all(r["refused"] for r in rs),
            "safe": [r.get("unanswerable_safe") for r in rs],
        }
    return out


def main() -> int:
    utf8_stdout()
    if len(sys.argv) < 3:
        print("用法: python -m eval.compare <base-prefix> <candidate-prefix>")
        return 2
    base = per_question(load_rounds(sys.argv[1]))
    cand = per_question(load_rounds(sys.argv[2]))
    common = [q for q in base if q in cand and base[q]["type"] in ("fact", "reasoning")]
    print(f"{sys.argv[2]} vs {sys.argv[1]}：可比可答题 {len(common)} 道（题级多轮均值）\n")

    for t in ("fact", "reasoning"):
        ids = [q for q in common if base[q]["type"] == t]
        deltas = [cand[q]["score"] - base[q]["score"] for q in ids
                  if base[q]["score"] is not None and cand[q]["score"] is not None]
        if deltas:
            print(f"{t:>9}: Δ均值 {st.mean(deltas):+.3f} | 变好 {sum(d > 0 for d in deltas)}"
                  f" | 变差 {sum(d < 0 for d in deltas)} | 不变 {sum(d == 0 for d in deltas)}")
    all_d = [cand[q]["score"] - base[q]["score"] for q in common
             if base[q]["score"] is not None and cand[q]["score"] is not None]
    print(f"{'合计':>8}: Δ均值 {st.mean(all_d):+.3f}（sd {st.pstdev(all_d):.3f}）\n")

    fixes = [q for q in common if base[q]["refused_all"] and not cand[q]["refused_all"]]
    regress = [q for q in common if not base[q]["refused_all"] and cand[q]["refused_all"]]
    print(f"误拒修复（基线多轮全拒 → 候选答出）: {len(fixes)} {fixes}")
    print(f"误拒新增（基线答出 → 候选多轮全拒）: {len(regress)} {regress}")

    print("\n变化最大的题：")
    ranked = sorted([(q, cand[q]["score"] - base[q]["score"]) for q in common
                     if base[q]["score"] is not None and cand[q]["score"] is not None],
                    key=lambda x: x[1])
    for q, d in ranked[:5]:
        print(f"  {q}: {base[q]['score']:.2f} → {cand[q]['score']:.2f} ({d:+.2f})  {base[q]['question'][:48]}")
    print("  ...")
    for q, d in ranked[-5:]:
        print(f"  {q}: {base[q]['score']:.2f} → {cand[q]['score']:.2f} ({d:+.2f})  {base[q]['question'][:48]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())