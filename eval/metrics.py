"""评估指标(纯函数,单测覆盖):recall@k 双口径、MRR、拒答率、faithfulness 聚合。"""

from __future__ import annotations


def recall_chunk(retrieved_ids: list[str], gold_id: str | None, k: int) -> int:
    """gold chunk 是否进入 top-k。命中记 1(供求和再平均)。"""
    if gold_id is None:
        return 0
    return int(gold_id in retrieved_ids[:k])


def recall_doc(retrieved_docs: list[str], gold_doc: str | None, k: int) -> int:
    if gold_doc is None:
        return 0
    return int(gold_doc in retrieved_docs[:k])


def reciprocal_rank(retrieved_ids: list[str], gold_id: str | None) -> float:
    """gold 首次出现的倒数排名;未出现记 0(MRR@k 由调用方截断)。"""
    if gold_id is None:
        return 0.0
    for i, cid in enumerate(retrieved_ids, 1):
        if cid == gold_id:
            return 1.0 / i
    return 0.0


def faithfulness_score(claims: list[dict] | None) -> float | None:
    """支持声明占比;claims 为空(未答/拒答/解析失败)返回 None,不计入均值。"""
    if not claims:
        return None
    return sum(1 for c in claims if c["supported"]) / len(claims)


def mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


def summarize(records: list[dict]) -> dict:
    """从 run 记录聚合全部指标。字段由 run_eval.py 写入:

    type / refused / retrieved_ids / retrieved_docs / gold_chunk_id / gold_doc
    correctness / correctness_noctx / faithfulness
    """
    answerable = [r for r in records if r["type"] in ("fact", "reasoning")]
    unanswerable = [r for r in records if r["type"] == "unanswerable"]
    out: dict = {"n": len(records)}

    out["recall@5_chunk"] = mean([recall_chunk(r["retrieved_ids"], r.get("gold_chunk_id"), 5) for r in answerable])
    out["recall@5_doc"] = mean([recall_doc(r["retrieved_docs"], r.get("gold_doc"), 5) for r in answerable])
    out["MRR"] = mean([reciprocal_rank(r["retrieved_ids"], r.get("gold_chunk_id")) for r in answerable])

    refused_answerable = sum(1 for r in answerable if r["refused"])
    refused_unanswerable = sum(1 for r in unanswerable if r["refused"])
    out["误拒率(可答题拒答)"] = round(refused_answerable / len(answerable), 4) if answerable else None
    out["正确拒答率(无法答题)"] = round(refused_unanswerable / len(unanswerable), 4) if unanswerable else None

    out["正确性"] = mean([r["correctness"] for r in answerable if r.get("correctness")])
    out["正确性_事实"] = mean([r["correctness"] for r in answerable if r["type"] == "fact" and r.get("correctness")])
    out["正确性_推理"] = mean([r["correctness"] for r in answerable if r["type"] == "reasoning" and r.get("correctness")])
    out["正确性_无检索对照"] = mean([r["correctness_noctx"] for r in answerable if r.get("correctness_noctx")])

    faith = [faithfulness_score(r.get("faithfulness")) for r in records if not r["refused"]]
    out["faithfulness"] = mean([f for f in faith if f is not None])
    out["faithfulness_n"] = sum(1 for f in faith if f is not None)
    return out
