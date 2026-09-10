"""介入点 A 材料：抽检 chunk 样例 + token/字符分布统计。

用法：
  python scripts/inspect_chunks.py [--jsonl data/chunks/chunks.jsonl] [--n 10]

产物（写入 data/chunks/）：
  samples.md  # 随机 N 个 chunk，含元数据、原文上下文（char_span 回切验证）
  stats.md    # chunk 数量、字符/嵌入 token 分布、章节深度分布
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.config import REPO_ROOT, get_settings
from pipeline.loader import load_doc


def percentile(sorted_vals: list[int], q: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def histogram(vals: list[int], edges: list[int]) -> list[str]:
    rows = []
    for lo, hi in zip(edges, edges[1:] + [float("inf")]):
        n = sum(1 for v in vals if lo <= v < hi)
        bar = "█" * max(1, round(n / max(1, len(vals)) * 60))
        rows.append(f"| {lo}-{hi if hi != float('inf') else '+'} | {n} | {bar} |")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=None, help="chunks.jsonl 路径（默认最新的全量文件）")
    ap.add_argument("--n", type=int, default=10, help="抽检 chunk 数")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    settings = get_settings()
    jsonl = Path(args.jsonl) if args.jsonl else settings.chunks_dir / "chunks.jsonl"
    records = [json.loads(line) for line in jsonl.open(encoding="utf-8")]
    print(f"读取 {len(records)} chunks ← {jsonl}")

    # ---- token 统计（bge-m3 分词器，即嵌入时真实截断口径）----
    print("加载 bge-m3 tokenizer 统计 token 分布...")
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(settings.embed_model)
    n_tokens = [len(tok.encode(r["text"], add_special_tokens=False)) for r in records]
    n_chars = [r["n_chars"] for r in records]
    st, sc = sorted(n_tokens), sorted(n_chars)

    stats_md = [
        "# Chunk 统计（Phase 1 基线：标题感知 512/50）",
        "",
        f"- 来源：`{jsonl.name}`，共 **{len(records)}** chunk，"
        f"覆盖 **{len({r['doc_name'] for r in records})}** 篇文档",
        f"- 字符总量 {sum(n_chars):,}；嵌入 token 总量 {sum(n_tokens):,}",
        "",
        "## 字符数分布",
        "",
        "| 指标 | min | p25 | 中位 | p75 | p95 | max |",
        "|---|---|---|---|---|---|---|",
        f"| 字符 | {sc[0]} | {percentile(sc, .25)} | {percentile(sc, .5)} | {percentile(sc, .75)} | {percentile(sc, .95)} | {sc[-1]} |",
        f"| token | {st[0]} | {percentile(st, .25)} | {percentile(st, .5)} | {percentile(st, .75)} | {percentile(st, .95)} | {st[-1]} |",
        "",
        "## token 直方图",
        "",
        "| 区间 | 数量 | 占比 |",
        "|---|---|---|",
        *histogram(n_tokens, [0, 64, 128, 192, 256, 320, 384, 448, 512]),
        "",
    ]

    over = [r for r, t in zip(records, n_tokens) if t > 512]
    stats_md += [
        f"超过 512 token 的 chunk：{len(over)}（bge-m3 上限 8192，无截断风险）",
        "",
        "## 章节深度分布（标题链层级数）",
        "",
        "| 深度 | chunk 数 |",
        "|---|---|",
    ]
    depth = Counter(len(r["section_path"].split(" > ")) if r["section_path"] else 0 for r in records)
    for d in sorted(depth):
        stats_md.append(f"| {d} | {depth[d]} |")

    stats_path = settings.chunks_dir / "stats.md"
    stats_path.write_text("\n".join(stats_md) + "\n", encoding="utf-8")
    print(f"  → {stats_path}")

    # ---- 抽检样例：char_span 回切原文，验证不变量 ----
    rng = random.Random(args.seed)
    picks = rng.sample(records, min(args.n, len(records)))
    # 按文档缓存 full_text
    doc_cache: dict[str, str] = {}
    lines = [f"# Chunk 抽检样例（seed={args.seed}，共抽 {len(picks)} 条）", ""]
    span_ok = 0
    for k, r in enumerate(picks, 1):
        if r["doc_name"] not in doc_cache:
            p = settings.corpus_root / r["doc_name"]
            doc_cache[r["doc_name"]] = load_doc(p, settings.corpus_root, settings.docs_src_root).full_text
        ft = doc_cache[r["doc_name"]]
        s, e = r["char_span"]
        original = ft[s:e]
        exact = original == r["text"]
        span_ok += exact
        context_head = ft[max(0, s - 80):s].replace("\n", "⏎")
        context_tail = ft[e:e + 80].replace("\n", "⏎")
        lines += [
            f"## 样例 {k}：`{r['chunk_id']}`",
            "",
            f"- 文档：`{r['doc_name']}`｜章节：**{r['section_path'] or '（无标题）'}**"
            f"｜char_span `[{s}, {e})`｜{r['n_chars']} 字符｜span 回切一致：{'✅' if exact else '❌'}",
            "",
            "**上文（前 80 字符）**：" f"`{context_head}`",
            "",
            "**chunk 全文**：",
            "",
            "```markdown",
            r["text"],
            "```",
            "",
            "**下文（后 80 字符）**：" f"`{context_tail}`",
            "",
            "---",
            "",
        ]
    lines.insert(1, f"\n> char_span 回切一致性：{span_ok}/{len(picks)} 通过\n")
    samples_path = settings.chunks_dir / "samples.md"
    samples_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → {samples_path}（span 回切 {span_ok}/{len(picks)} 通过）")


if __name__ == "__main__":
    main()
