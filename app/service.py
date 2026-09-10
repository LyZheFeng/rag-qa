"""RAG 编排：检索 → 生成 → 汇总（引用富化 + 延迟）。"""

from __future__ import annotations

import time
from functools import lru_cache

from .generator import LLMGenerator
from .retriever import VectorRetriever
from .schemas import AskResponse, Hit, Latency


class RagService:
    def __init__(self, retriever: VectorRetriever, generator: LLMGenerator):
        self.retriever = retriever
        self.generator = generator

    def ask(self, question: str, k: int = 5) -> AskResponse:
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, k=k)
        t1 = time.perf_counter()

        if not hits:
            return AskResponse(
                question=question,
                answer="未检索到任何相关资料，无法回答。",
                refused=True,
                parse_mode="json",
                cited=[],
                retrieved=[],
                latency=Latency(retrieve_ms=_ms(t1 - t0), generate_ms=0, total_ms=_ms(t1 - t0)),
            )

        outcome = self.generator.generate(question, hits)
        t2 = time.perf_counter()

        by_index = {h.index: h for h in hits}
        cited = [by_index[i] for i in outcome.spec.citations if i in by_index]
        return AskResponse(
            question=question,
            answer=outcome.spec.answer,
            refused=outcome.spec.refused,
            parse_mode=outcome.parse_mode,
            cited=cited,
            retrieved=hits,
            latency=Latency(retrieve_ms=_ms(t1 - t0), generate_ms=_ms(t2 - t1), total_ms=_ms(t2 - t0)),
        )


def _ms(seconds: float) -> int:
    return int(seconds * 1000)


@lru_cache(maxsize=1)
def get_service() -> RagService:
    """进程内单例（FastAPI lifespan / Streamlit cache 共用）。"""
    from .retriever import get_retriever

    return RagService(get_retriever(), LLMGenerator.from_settings())
