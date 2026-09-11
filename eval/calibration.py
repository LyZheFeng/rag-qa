"""Phase 5 拒答校准:匹配分阈值扫描 vs LLM 自主拒答工作点。

问题:当前拒答由 LLM 看上下文自主决定(v0.2:误拒 7.5%/正确拒答 100%)。
本脚本回答:如果加一道"top-1 匹配分 < t 则强制拒答"的闸门,权衡曲线长什么样,
LLM 工作点是否已被支配。曲线与结论留档 eval/calibration.md。
"""

from __future__ import annotations

import json
import sys

from .common import DATA_EVAL, REPO_ROOT, ensure_dirs, load_jsonl, utf8_stdout


def main() -> None:
    utf8_stdout()
    ensure_dirs()
    questions = load_jsonl(DATA_EVAL / "questions.jsonl")

    from pipeline.config import get_settings
    from app.hybrid import BM25Index, HybridRetriever
    from app.retriever import VectorRetriever

    s = get_settings()
    hybrid = HybridRetriever(
        VectorRetriever.from_settings(), BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k
    )

    rows = []
    for i, q in enumerate(questions, 1):
        hits = hybrid.retrieve(q["question"], k=5)
        rows.append({"qid": q["qid"], "type": q["type"], "top1": hits[0].score if hits else 0.0})
        if i % 50 == 0:
            print(f"检索 {i}/{len(questions)}", flush=True)

    (DATA_EVAL / "calibration_scores.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8"
    )

    ans = [r for r in rows if r["type"] != "unanswerable"]
    unans = [r for r in rows if r["type"] == "unanswerable"]
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60]
    lines = [
        "# 拒答校准曲线(2026-09-11,v0.2-hybrid)",
        "",
        f"数据:200 题全量检索(可答 {len(ans)} / 无法回答 {len(unans)}),top-1 匹配分(hybrid RRF 归一化)。",
        "",
        "| 阈值 t(top1<t 强制拒答) | 误拒率(可答题) | 正确拒答率(无法答题) |",
        "|---|---|---|",
    ]
    for t in thresholds:
        fr = sum(1 for r in ans if r["top1"] < t) / len(ans)
        cr = sum(1 for r in unans if r["top1"] < t) / len(unans)
        lines.append(f"| {t:.2f} | {fr:.1%} | {cr:.1%} |")
        print(f"t={t:.2f} 误拒 {fr:.1%} 正确拒答 {cr:.1%}")
    lines += [
        "",
        "**对照:LLM 自主拒答工作点(v0.2 全量实测)= 误拒 7.5% / 正确拒答 100%**",
        "",
        "## 结论",
        "",
        "- 待填(脚本输出后按数据写)",
    ]
    (REPO_ROOT / "eval" / "calibration.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n已写 eval/calibration.md")


if __name__ == "__main__":
    sys.exit(main())
