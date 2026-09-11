"""v0.5 切块策略对比:heading(现役) vs fixed vs parent-child。

切块不同则 chunk_id 体系不同,chunk 口径指标不可比;统一用 **doc 口径**:
recall@5_doc(正确文档进 top-5)与 doc-MRR(正确文档首次出现的倒数排名)。
胜出者再走端到端全量评估(run_eval)。
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .common import DATA_EVAL, RUNS_DIR, ensure_dirs, load_jsonl, utf8_stdout
from .metrics import mean


def doc_rr(docs: list[str], gold_doc: str | None) -> float:
    if gold_doc is None:
        return 0.0
    for i, d in enumerate(docs, 1):
        if d == gold_doc:
            return 1.0 / i
    return 0.0


def evaluate(retriever, name: str, questions: list[dict]) -> dict:
    out_dir = RUNS_DIR / "retrieval_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"chunking_{name}.jsonl"
    done = {r["qid"]: r for r in load_jsonl(path)}
    f = open(path, "a", encoding="utf-8")
    r5, rr, n = 0, 0.0, 0
    for i, q in enumerate(questions, 1):
        if q["qid"] not in done:
            t0 = time.time()
            hits = retriever.retrieve(q["question"], k=5)
            rec = {"qid": q["qid"], "docs": [h.doc_name for h in hits], "elapsed_ms": int((time.time() - t0) * 1000)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            done[q["qid"]] = rec
        docs = done[q["qid"]]["docs"]
        r5 += int(q["gold_doc"] in docs[:5])
        rr += doc_rr(docs, q["gold_doc"])
        n += 1
        if i % 20 == 0:
            print(f"  [{name}] {i}/{len(questions)} doc-recall@5={r5 / n:.3f}", flush=True)
    f.close()
    return {"recall@5_doc": round(r5 / n, 4), "doc_MRR": round(rr / n, 4), "n": n}


def main() -> None:
    utf8_stdout()
    ensure_dirs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", default="heading,fixed,parentchild")
    args = parser.parse_args()

    from pipeline.config import get_settings

    s = get_settings()
    questions = [q for q in load_jsonl(DATA_EVAL / "questions.jsonl") if q["type"] != "unanswerable"]
    print(f"可答题 {len(questions)} 道,doc 口径对比,变体: {args.variants}")

    from app.hybrid import BM25Index, HybridRetriever
    from app.retriever import VectorRetriever

    wanted = args.variants.split(",")

    def hybrid_for(collection: str, chunks_file):
        return HybridRetriever(
            VectorRetriever.from_settings(collection), BM25Index.from_chunks_file(chunks_file), s.hybrid_candidates, s.rrf_k
        )

    if "heading" in wanted:
        print("heading(现役 v0.2)", evaluate(hybrid_for(s.collection, s.chunks_path), "heading", questions), flush=True)
    if "fixed" in wanted:
        print("fixed-512-50", evaluate(hybrid_for("fastapi_zh_fixed", s.chunks_dir / "chunks_fixed.jsonl"), "fixed", questions), flush=True)
    if "parentchild" in wanted:
        from app.parentchild import ParentChildRetriever, build_pc_maps

        child = hybrid_for("fastapi_zh_pc", s.chunks_dir / "chunks_pc.jsonl")
        c2p, parents = build_pc_maps(s.chunks_dir)
        pc = ParentChildRetriever(child, c2p, parents, candidates=s.hybrid_candidates)
        print("parent-child(子256/父整节)", evaluate(pc, "parentchild", questions), flush=True)


if __name__ == "__main__":
    sys.exit(main())
