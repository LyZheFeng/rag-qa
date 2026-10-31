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
    # 安全口径：refused=true，或 judge 判定「明确声明资料缺失且未编造」；
    # 仅统计有判定的记录（新 run 全量有，旧 run 需 eval/backfill_safe.py 回填）
    safe_flags = [r.get("unanswerable_safe") for r in unanswerable if r.get("unanswerable_safe") is not None]
    out["安全作答率(无法答题)"] = round(sum(1 for x in safe_flags if x) / len(safe_flags), 4) if safe_flags else None
    out["安全作答率_n"] = len(safe_flags)

    out["正确性"] = mean([r["correctness"] for r in answerable if r.get("correctness") is not None])
    out["正确性_事实"] = mean([r["correctness"] for r in answerable if r["type"] == "fact" and r.get("correctness") is not None])
    out["正确性_推理"] = mean([r["correctness"] for r in answerable if r["type"] == "reasoning" and r.get("correctness") is not None])
    out["正确性_无检索对照"] = mean([r["correctness_noctx"] for r in answerable if r.get("correctness_noctx") is not None])
    # 分母透明化:0 分恰好是 judge 解析失败/越界(1~5 之外),必须计入均值而不是丢弃
    out["正确性_n"] = sum(1 for r in answerable if r.get("correctness") is not None)
    out["judge_zero"] = sum(1 for r in answerable if r.get("correctness") == 0)
    out["judge_missing"] = sum(1 for r in answerable if r.get("correctness") is None)

    faith = [faithfulness_score(r.get("faithfulness")) for r in records if not r["refused"]]
    out["faithfulness"] = mean([f for f in faith if f is not None])
    out["faithfulness_n"] = sum(1 for f in faith if f is not None)
    return out
