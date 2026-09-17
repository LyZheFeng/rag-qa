"""RAG 编排：检索 → 生成 → 汇总（引用富化 + 延迟）。

流式（ask_stream）产出 (event, payload) 二元组，SSE 语义在 api 层编码：
  sources → 检索完成（全部命中）；delta → 临时增量文本；retry → 要求清空重打；
  done → 权威终态（完整 AskResponse）。error 由 api 层统一捕获下发。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from functools import lru_cache

from .generator import LLMGenerator
from .retriever import VectorRetriever
from .schemas import AnswerSpec, AskResponse, Hit, Latency


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

    def ask_stream(self, question: str, k: int = 5) -> Iterator[tuple[str, dict]]:
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, k=k)
        t1 = time.perf_counter()
        yield "sources", {"hits": [h.model_dump() for h in hits]}

        if not hits:
            yield "done", self._summarize(
                question,
                [],
                _empty_spec("未检索到任何相关资料，无法回答。"),
                "json",
                _ms(t1 - t0),
                0,
            ).model_dump()
            return

        outcome = None
        for item in self.generator.generate_stream(question, hits):
            if item.kind == "delta":
                yield "delta", {"text": item.text}
            elif item.kind == "retry":
                yield "retry", {"message": "输出格式异常，正在重试"}
            else:
                outcome = item.outcome
        t2 = time.perf_counter()
        assert outcome is not None  # generate_stream 契约：最后必有 outcome
        yield "done", self._summarize(
            question, hits, outcome.spec, outcome.parse_mode, _ms(t1 - t0), _ms(t2 - t1)
        ).model_dump()

    @staticmethod
    def _summarize(question: str, hits: list[Hit], spec: AnswerSpec, parse_mode: str,
                   retrieve_ms: int, generate_ms: int) -> AskResponse:
        by_index = {h.index: h for h in hits}
        cited = [by_index[i] for i in spec.citations if i in by_index]
        return AskResponse(
            question=question,
            answer=spec.answer,
            refused=spec.refused,
            parse_mode=parse_mode,
            cited=cited,
            retrieved=hits,
            latency=Latency(
                retrieve_ms=retrieve_ms, generate_ms=generate_ms, total_ms=retrieve_ms + generate_ms
            ),
        )


def _ms(seconds: float) -> int:
    return int(seconds * 1000)


def _empty_spec(answer: str) -> AnswerSpec:
    return AnswerSpec(answer=answer, citations=[], refused=True)


@lru_cache(maxsize=1)
def get_service() -> RagService:
    """进程内单例（FastAPI lifespan / 各入口共用）。"""
    from .retriever import get_retriever

    return RagService(get_retriever(), LLMGenerator.from_settings())
