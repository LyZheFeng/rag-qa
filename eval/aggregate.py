"""把同一候选的多轮 run 汇总成均值±标准差表。

用法:
    python -m eval.aggregate v0.9-inference          # 匹配 v0.9-inference_* 与 v0.9-inference-r*
    python -m eval.aggregate v0.7-retry20

只读 records.jsonl，不写文件；轮次按目录名/修改时间排序。指标口径与 `metrics.summarize` 一致。
"""

from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

from .common import RUNS_DIR, load_jsonl, utf8_stdout
from .metrics import summarize

ROWS = [
    ("正确性", "正确性", "f"),
    ("└ 事实", "正确性_事实", "f"),
    ("└ 推理", "正确性_推理", "f"),
    ("无检索对照", "正确性_无检索对照", "f"),
    ("误拒率(可答题)", "误拒率(可答题拒答)", "p"),
    ("正确拒答率(无法答题)", "正确拒答率(无法答题)", "p"),
    ("安全作答率(无法答题)", "安全作答率(无法答题)", "p"),
    ("recall@5 chunk", "recall@5_chunk", "f"),
    ("recall@5 doc", "recall@5_doc", "f"),
    ("MRR", "MRR", "f"),
    ("faithfulness", "faithfulness", "f"),
]


def find_rounds(prefix: str) -> list[Path]:
    dirs = [
        p for p in RUNS_DIR.iterdir()
        if p.is_dir() and (p / "records.jsonl").exists()
        and (p.name.startswith(prefix + "_") or p.name.startswith(prefix + "-r"))
    ]
    return sorted(dirs, key=lambda p: p.stat().st_mtime)


def _fmt(v: float | None, kind: str) -> str:
    if v is None:
        return "—"
    return f"{v:.2%}" if kind == "p" else f"{v:.4f}"


def main() -> int:
    utf8_stdout()
    if len(sys.argv) < 2:
        print("用法: python -m eval.aggregate <version-prefix>")
        return 2
    prefix = sys.argv[1]
    dirs = find_rounds(prefix)
    if not dirs:
        print(f"没有找到 {prefix} 的 run 目录")
        return 1
    labels = [f"r{i}" for i in range(1, len(dirs) + 1)]
    summaries = []
    print(f"候选 {prefix}：{len(dirs)} 轮")
    for d in dirs:
        recs = load_jsonl(d / "records.jsonl")
        s = summarize(recs)
        s["_latency_ms"] = round(
            st.mean([r["retrieve_ms"] + r["generate_ms"] for r in recs]) if recs else 0
        )
        s["_retried"] = sum(1 for r in recs if r.get("retried"))
        s["_rewritten"] = sum(1 for r in recs if r.get("rewritten"))
        s["_errors"] = sum(1 for r in recs if r.get("error"))
        summaries.append(s)
        print(f"  {d.name} | n={s['n']} | 延迟均值 {s['_latency_ms']}ms"
              f" | retried {s['_retried']} | rewritten {s['_rewritten']} | 异常 {s['_errors']}")

    print()
    header = f"{'指标':<22}" + "".join(f"{lab:>10}" for lab in labels) + f"{'均值±标准差':>18}"
    print(header)
    for title, key, kind in ROWS:
        vals = [s.get(key) for s in summaries]
        nums = [v for v in vals if v is not None]
        mean = st.mean(nums) if nums else None
        sd = st.pstdev(nums) if len(nums) > 1 else 0.0
        cells = "".join(f"{_fmt(v, kind):>10}" for v in vals)
        if mean is None:
            tail = "—".rjust(18)
        elif kind == "p":
            tail = f"{mean:.2%} ± {sd * 100:.2f}pp".rjust(18)
        else:
            tail = f"{mean:.4f} ± {sd:.4f}".rjust(18)
        print(f"{title:<22}{cells}{tail}")

    lat = [s["_latency_ms"] for s in summaries]
    print(f"\n延迟均值 {st.mean(lat):.0f}ms | retried 合计 {sum(s['_retried'] for s in summaries)}"
          f" | rewritten 合计 {sum(s['_rewritten'] for s in summaries)}"
          f" | 跑批异常合计 {sum(s['_errors'] for s in summaries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())