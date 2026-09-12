"""Phase 1 管道 CLI：load → clean → chunk →（可选）embed → Chroma。

用法：
  python scripts/build_index.py                    # 全量：chunk + 嵌入 + 入库
  python scripts/build_index.py --limit 5          # 冒烟：只处理 5 篇
  python scripts/build_index.py --no-embed         # 只产出 chunks.jsonl（改 chunker 调参时用）
  python scripts/build_index.py --collection NAME  # 换 collection 做对比实验（v0.5-chunking）

产物：
  data/chunks/chunks.jsonl   # 中间产物，Phase 3 抽题 & 抽检脚本的输入
  data/chroma/               # Chroma 持久库
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.chunker import ChunkStrategy, HeadingAwareChunker
from pipeline.config import get_settings
from pipeline.loader import iter_corpus, load_doc
from pipeline.models import Chunk
from pipeline.store import get_collection, upsert_chunks


def build_chunks(strategy: ChunkStrategy, limit: int | None) -> tuple[list[Chunk], dict]:
    settings = get_settings()
    paths = iter_corpus(settings.corpus_root)
    if limit:
        paths = paths[:limit]
    all_chunks: list[Chunk] = []
    stats = {
        "docs": 0,
        "blocks": 0,
        "code_blocks": 0,
        "placeholders_resolved": 0,
        "includes_resolved": 0,
        "unresolved_refs": 0,
    }
    for p in paths:
        doc = load_doc(p, settings.corpus_root, settings.docs_src_root)
        from pipeline.cleaner import LAST_STATS

        stats["placeholders_resolved"] += LAST_STATS["placeholders_resolved"]
        stats["includes_resolved"] += LAST_STATS["includes_resolved"]
        stats["unresolved_refs"] += LAST_STATS["unresolved"]
        stats["blocks"] += len(doc.blocks)
        stats["code_blocks"] += sum(1 for b in doc.blocks if b.kind == "code")
        all_chunks.extend(strategy.chunk(doc))
        stats["docs"] += 1
    stats["chunks"] = len(all_chunks)
    stats["chars_total"] = sum(c.n_chars for c in all_chunks)
    return all_chunks, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 篇文档（冒烟）")
    ap.add_argument("--size", type=int, default=512, help="chunk 字符数上限")
    ap.add_argument("--overlap", type=int, default=50, help="chunk 重叠字符数")
    ap.add_argument("--strategy", default="heading", choices=["heading", "fixed"], help="切块策略（v0.5 对比）")
    ap.add_argument("--tag", default="", help="产物 jsonl 后缀标记（chunks_{tag}.jsonl，默认覆盖主文件）")
    ap.add_argument("--collection", default="fastapi_zh_v1", help="Chroma collection 名（实验对比用）")
    ap.add_argument("--no-embed", action="store_true", help="只产出 chunks.jsonl，不嵌入不入库")
    args = ap.parse_args()

    settings = get_settings()
    t0 = time.time()
    print(f"[1/3] 加载 + 清洗 + 切块（strategy={args.strategy} size={args.size}/overlap={args.overlap}）...")
    from pipeline.chunker import FixedChunker

    strategy = (
        HeadingAwareChunker(size=args.size, overlap=args.overlap)
        if args.strategy == "heading"
        else FixedChunker(size=args.size, overlap=args.overlap)
    )
    chunks, stats = build_chunks(strategy, args.limit)

    out_dir = settings.chunks_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = ["chunks"]
    if args.tag:
        parts.append(args.tag)
    if args.limit:
        parts.append(f"L{args.limit}")
    jsonl_path = out_dir / ("_".join(parts) + ".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_record(), ensure_ascii=False) + "\n")

    dup_hashes = stats["chunks"] - len({c.hash for c in chunks})
    print(
        f"  文档 {stats['docs']} 篇 | 块 {stats['blocks']}（代码 {stats['code_blocks']}）"
        f" | chunk {stats['chunks']}（跨文档同 hash {dup_hashes}）"
    )
    print(
        f"  占位符解析 {stats['placeholders_resolved']} | include 解析 {stats['includes_resolved']}"
        f" | 未解析引用 {stats['unresolved_refs']}"
    )
    print(f"  → {jsonl_path}")

    if args.no_embed:
        print(f"完成（--no-embed），耗时 {time.time() - t0:.1f}s")
        return

    print(f"[2/3] bge-m3 嵌入 {len(chunks)} 条（CPU）...")
    from pipeline.embed import BgeM3Embedder

    embedder = BgeM3Embedder(settings.embed_model)
    print(f"  模型就绪，维度 {embedder.dim}")
    embeddings = embedder.encode_corpus([c.text for c in chunks])

    print(f"[3/3] 写入 Chroma collection={args.collection} ...")
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    col = get_collection(settings.chroma_dir, args.collection)
    n = upsert_chunks(col, chunks, embeddings)
    print(f"  upsert {n} 条，库内共 {col.count()} 条 → {settings.chroma_dir}")

    # 主线构建才写 manifest（实验 tag/自定义 collection 不碰，防污染主索引绑定关系）
    if jsonl_path == settings.chunks_path and args.collection == settings.collection:
        from pipeline.manifest import write_manifest

        mp = write_manifest(
            settings.chroma_dir, jsonl_path,
            collection=args.collection, embed_model=settings.embed_model, chunk_count=col.count(),
        )
        print(f"  manifest → {mp}")
    print(f"完成，耗时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
