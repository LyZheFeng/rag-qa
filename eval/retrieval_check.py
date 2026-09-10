"""检索层快速对比(无 LLM):vector vs hybrid 在测试集可答题上的 recall/MRR。

v0.x 迭代的第一个信号源——检索没提升就不必浪费 LLM 评估。
"""

from __future__ import annotations

import sys

from .common import DATA_EVAL, REPO_ROOT, ensure_dirs, load_jsonl, utf8_stdout
from .metrics import mean, recall_chunk, recall_doc, reciprocal_rank


def evaluate(retriever, questions: list[dict]) -> dict:
    rows = []
    for q in questions:
        hits = retriever.retrieve(q["question"], k=10)
        ids = [h.chunk_id for h in hits]
        docs = [h.doc_name for h in hits]
        rows.append((ids, docs, q))
    return {
        "recall@5_chunk": mean([recall_chunk(i, q.get("gold_chunk_id"), 5) for i, d, q in rows]),
        "recall@10_chunk": mean([recall_chunk(i, q.get("gold_chunk_id"), 10) for i, d, q in rows]),
        "recall@5_doc": mean([recall_doc(d, q.get("gold_doc"), 5) for i, d, q in rows]),
        "MRR": mean([reciprocal_rank(i, q.get("gold_chunk_id")) for i, d, q in rows]),
    }


def main() -> None:
    utf8_stdout()
    ensure_dirs()
    from pipeline.config import get_settings

    questions = [q for q in load_jsonl(DATA_EVAL / "questions.jsonl") if q["type"] != "unanswerable"]
    print(f"可答题 {len(questions)} 道(事实+推理)")

    from app.retriever import VectorRetriever, get_retriever

    vector = VectorRetriever.from_settings()
    s = get_settings()
    from app.hybrid import BM25Index, HybridRetriever

    hybrid = HybridRetriever(vector, BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k)

    for name, retr in (("vector(v0.1)", get_retriever()), ("hybrid(v0.2)", hybrid)):
        m = evaluate(retr, questions)
        print(f"{name:14} " + "  ".join(f"{k}={v}" for k, v in m.items()), flush=True)


if __name__ == "__main__":
    sys.exit(main())
