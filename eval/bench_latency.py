"""测量流式首字延迟（TTFT）与端到端延迟，供 README 性能章节使用。

用法:
    python -m eval.bench_latency            # 50 题：20 fact + 20 reasoning + 10 unanswerable
    python -m eval.bench_latency --n 100

只跑流式（与网页同一条路径），不改数据、不写文件。TTFT = 第一个 delta 到达的时间，
retrieve_ms/generate_ms 取自 done 事件里的 latency（generate_ms 含二次检索与改写）。
"""

from __future__ import annotations

import argparse
import statistics as st
import time
from pathlib import Path

from app.service import get_service
from .common import REPO_ROOT, load_jsonl, utf8_stdout


def sample(n: int) -> list[dict]:
    qs = load_jsonl(REPO_ROOT / "data" / "eval" / "questions.jsonl")
    by = {"fact": [], "reasoning": [], "unanswerable": []}
    for q in qs:
        by.setdefault(q["type"], []).append(q)
    # 按比例分层，至少各 1 道
    parts = {"fact": round(n * 0.4), "reasoning": round(n * 0.4)}
    parts["unanswerable"] = max(1, n - parts["fact"] - parts["reasoning"])
    out: list[dict] = []
    for t, k in parts.items():
        out += by.get(t, [])[:k]
    return out


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    svc = get_service()
    rows = []
    for q in sample(args.n):
        t0 = time.perf_counter()
        ttft = None
        done = None
        for event, payload in svc.ask_stream(q["question"]):
            if event == "delta" and ttft is None:
                ttft = time.perf_counter() - t0
            elif event == "done":
                done = payload
        total = time.perf_counter() - t0
        rows.append({
            "qid": q["qid"],
            "type": q["type"],
            "ttft_ms": round((ttft or total) * 1000),
            "total_ms": round(total * 1000),
            "retried": bool(done and done.get("retried")),
            "rewritten": bool(done and done.get("rewritten")),
        })
        print(f"{q['qid']} {rows[-1]['ttft_ms']:5d}ms / {rows[-1]['total_ms']:5d}ms"
              f" retried={rows[-1]['retried']} rewritten={rows[-1]['rewritten']}", flush=True)

    def pct(vals: list[int], p: float) -> int:
        vals = sorted(vals)
        idx = min(len(vals) - 1, int(round((len(vals) - 1) * p)))
        return vals[idx]

    print(f"\n样本 {len(rows)} 题 | 首字(TTFT) p50 {pct([r['ttft_ms'] for r in rows], 0.5)}ms"
          f" p90 {pct([r['ttft_ms'] for r in rows], 0.9)}ms"
          f" 均值 {st.mean([r['ttft_ms'] for r in rows]):.0f}ms")
    print(f"端到端 p50 {pct([r['total_ms'] for r in rows], 0.5)}ms"
          f" p90 {pct([r['total_ms'] for r in rows], 0.9)}ms"
          f" 均值 {st.mean([r['total_ms'] for r in rows]):.0f}ms")
    print(f"二次检索 {sum(r['retried'] for r in rows)} | 改写 {sum(r['rewritten'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())