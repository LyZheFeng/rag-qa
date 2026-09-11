"""检索层快速对比(无 LLM):vector / hybrid / rerank 在测试集可答题上的 recall/MRR。

v0.3 教训后的改造:
- 每题结果增量落盘 eval/runs/retrieval_check/{name}.jsonl,断点续跑(跳过已完成 qid)
- --retrievers 选择要跑的路(如只补 rerank:--retrievers rerank)
- --limit N 先小样本实测耗时再决定是否全量

v0.x 迭代的第一个信号源——检索没提升就不必浪费 LLM 评估。
"""

from __future__ import annotations

import argparse
import json
import sys

from .common import DATA_EVAL, RUNS_DIR, ensure_dirs, load_jsonl, utf8_stdout
from .metrics import mean, recall_chunk, recall_doc, reciprocal_rank


def evaluate(retriever, name: str, questions: list[dict]) -> dict:
    out_dir = RUNS_DIR / "retrieval_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.jsonl"
    done = {r["qid"]: r for r in load_jsonl(path)}
    f = open(path, "a", encoding="utf-8")
    rows = []
    import time

    for i, q in enumerate(questions, 1):
        if q["qid"] not in done:
            t0 = time.time()
            hits = retriever.retrieve(q["question"], k=10)
            rec = {
                "qid": q["qid"],
                "ids": [h.chunk_id for h in hits],
                "docs": [h.doc_name for h in hits],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            done[q["qid"]] = rec
        r = done[q["qid"]]
        rows.append((r["ids"], r["docs"], q))
        if i % 10 == 0:
            ms = mean([done[q["qid"]]["elapsed_ms"] for q in questions[:i] if q["qid"] in done])
            print(f"  [{name}] {i}/{len(questions)} 单题均值 {ms:.0f}ms", flush=True)
    f.close()
    elapsed = [done[q["qid"]]["elapsed_ms"] for q in questions if q["qid"] in done]
    return {
        "recall@5_chunk": mean([recall_chunk(i, q.get("gold_chunk_id"), 5) for i, d, q in rows]),
        "recall@10_chunk": mean([recall_chunk(i, q.get("gold_chunk_id"), 10) for i, d, q in rows]),
        "recall@5_doc": mean([recall_doc(d, q.get("gold_doc"), 5) for i, d, q in rows]),
        "MRR": mean([reciprocal_rank(i, q.get("gold_chunk_id")) for i, d, q in rows]),
        "单题均值ms": round(mean(elapsed)) if elapsed else 0,
        "n": len(rows),
    }


def main() -> None:
    utf8_stdout()
    ensure_dirs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrievers", default="vector,hybrid,rerank")
    parser.add_argument("--limit", type=int, default=0, help="先跑前 N 题实测耗时(0=全量)")
    args = parser.parse_args()

    questions = [q for q in load_jsonl(DATA_EVAL / "questions.jsonl") if q["type"] != "unanswerable"]
    if args.limit:
        questions = questions[: args.limit]
        print(f"小样本实测:前 {len(questions)} 题")
    print(f"可答题 {len(questions)} 道(事实+推理),跑 {args.retrievers}")

    from pipeline.config import get_settings
    from app.retriever import VectorRetriever

    s = get_settings()
    vector = VectorRetriever.from_settings()

    wanted = args.retrievers.split(",")
    if "vector" in wanted:
        print("vector(v0.1)", evaluate(vector, "vector", questions), flush=True)
    if "hybrid" in wanted:
        from app.hybrid import BM25Index, HybridRetriever

        hybrid = HybridRetriever(vector, BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k)
        print("hybrid(v0.2)", evaluate(hybrid, "hybrid", questions), flush=True)
    if "rerank" in wanted:
        from app.hybrid import BM25Index, HybridRetriever
        from app.rerank import RerankRetriever

        hybrid = HybridRetriever(vector, BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k)
        rerank = RerankRetriever(hybrid, candidates=s.hybrid_candidates)
        print("rerank(v0.3)", evaluate(rerank, "rerank", questions), flush=True)


if __name__ == "__main__":
    sys.exit(main())
