"""v0.3-rerank:hybrid 粗排 N=20 → bge-reranker-v2-m3 精排 top-k。

动机:v0.2 检索层 recall@10_chunk 已 93.1%,瓶颈从"召回"转为"排序"——
精排把 20 候选里正确段落顶进 top-5。RETRIEVER=rerank 启用。
"""

from __future__ import annotations

import math
from functools import lru_cache

from .schemas import Hit


@lru_cache(maxsize=1)
def get_reranker():
    """CrossEncoder 单例:CPU 加载约 4 分钟,进程内只付一次。"""
    from sentence_transformers import CrossEncoder

    from pipeline.config import get_settings

    return CrossEncoder(get_settings().rerank_model, max_length=512)


class RerankRetriever:
    """粗排(hybrid)N 候选 → rerank 打分 → top-k。接口与 VectorRetriever 一致。"""

    def __init__(self, base, reranker=None, candidates: int = 20):
        self.base = base
        self.reranker = reranker if reranker is not None else get_reranker()
        self.candidates = candidates

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        pool = self.base.retrieve(query, k=self.candidates)
        if len(pool) <= k:
            return pool
        scores = self.reranker.predict([(query, h.text) for h in pool])
        ranked = sorted(zip(pool, scores), key=lambda x: -float(x[1]))[:k]
        hits: list[Hit] = []
        for rank, (h, s) in enumerate(ranked, 1):
            # CrossEncoder 输出原始 logit(可正可负),过 sigmoid 转成 0~1 匹配度供展示
            raw = float(s)
            prob = 1.0 / (1.0 + math.exp(-raw)) if -60 < raw < 60 else (1.0 if raw > 0 else 0.0)
            hits.append(h.model_copy(update={"index": rank, "score": round(prob, 4)}))
        return hits
