"""RAG 编排：检索 → 生成 → 汇总（引用富化 + 延迟）。

流式（ask_stream）产出 (event, payload) 二元组，SSE 语义在 api 层编码：
  sources → 检索完成（全部命中）；delta → 临时增量文本；retry → 要求清空重打；
  done → 权威终态（完整 AskResponse）。error 由 api 层统一捕获下发。

拒答兜底（v0.7）：首轮 refused=true 且 retry_k 比首轮 k 更深时，按 retry_k 重新检索、
用更大的上下文重答一次（流式事件序 retry → sources → delta*）。二次答出返回二次结果，
仍拒答则保留首轮结果。hybrid 内部本就召回 hybrid_candidates 条再融合，加深 k 只让
prompt 变长，不增加检索耗时；只在拒答（约 8%）时走这条支路。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from functools import lru_cache

from .generator import GenerationOutcome, LLMGenerator
from .retriever import VectorRetriever
from .schemas import AnswerSpec, AskResponse, Hit, Latency

# 拒答后扩大检索重答时下发给前端的提示（generator 的格式重试另有文案）
RETRY_MESSAGE = "资料不足，扩大检索范围后重答"


class RagService:
    def __init__(self, retriever: VectorRetriever, generator: LLMGenerator, retry_k: int = 20):
        self.retriever = retriever
        self.generator = generator
        self.retry_k = retry_k  # 0 = 关闭拒答兜底

    def _deeper_retry_k(self, k: int) -> int:
        """需要二次检索时返回更深的 k；关闭或不够深（无新资料）返回 0。"""
        return self.retry_k if self.retry_k > k else 0

    def ask(self, question: str, k: int = 5) -> AskResponse:
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, k=k)
        t1 = time.perf_counter()
        retrieve_ms = _ms(t1 - t0)

        if not hits:
            return AskResponse(
                question=question,
                answer="未检索到任何相关资料，无法回答。",
                refused=True,
                parse_mode="json",
                cited=[],
                retrieved=[],
                latency=Latency(retrieve_ms=retrieve_ms, generate_ms=0, total_ms=retrieve_ms),
            )

        outcome = self.generator.generate(question, hits)
        generate_ms = _ms(time.perf_counter() - t1)

        # 误拒兜底：首轮拒答 → 更深检索 → 上下文真的变多才重答（否则白烧一次生成）
        retried = False
        retry_k = self._deeper_retry_k(k)
        if retry_k and outcome.spec.refused:
            t_ret = time.perf_counter()
            more = self.retriever.retrieve(question, k=retry_k)
            retrieve_ms += _ms(time.perf_counter() - t_ret)
            if len(more) > len(hits):
                retried = True
                t_gen = time.perf_counter()
                second = self.generator.generate(question, more)
                generate_ms += _ms(time.perf_counter() - t_gen)
                if not second.spec.refused:
                    hits, outcome = more, second

        by_index = {h.index: h for h in hits}
        cited = [by_index[i] for i in outcome.spec.citations if i in by_index]
        return AskResponse(
            question=question,
            answer=outcome.spec.answer,
            refused=outcome.spec.refused,
            retried=retried,
            parse_mode=outcome.parse_mode,
            cited=cited,
            retrieved=hits,
            latency=Latency(
                retrieve_ms=retrieve_ms,
                generate_ms=generate_ms,
                total_ms=_ms(time.perf_counter() - t0),
            ),
        )

    def ask_stream(self, question: str, k: int = 5) -> Iterator[tuple[str, dict]]:
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, k=k)
        retrieve_ms = _ms(time.perf_counter() - t0)
        yield "sources", {"hits": [h.model_dump() for h in hits]}

        if not hits:
            yield "done", self._summarize(
                question,
                [],
                _empty_spec("未检索到任何相关资料，无法回答。"),
                "json",
                retrieve_ms,
                0,
            ).model_dump()
            return

        t_gen = time.perf_counter()
        outcome: GenerationOutcome | None = None
        for event, payload in self._stream_round(question, hits):
            if event == "outcome":
                outcome = payload
            else:
                yield event, payload
        generate_ms = _ms(time.perf_counter() - t_gen)
        assert outcome is not None  # generate_stream 契约：最后必有 outcome

        retried = False
        retry_k = self._deeper_retry_k(k)
        if retry_k and outcome.spec.refused:
            t_ret = time.perf_counter()
            more = self.retriever.retrieve(question, k=retry_k)
            retrieve_ms += _ms(time.perf_counter() - t_ret)
            if len(more) > len(hits):
                retried = True
                # 先 retry 让前端清空上一轮的拒答文本，再推新的命中集重答
                yield "retry", {"message": RETRY_MESSAGE}
                first_hits, hits = hits, more
                yield "sources", {"hits": [h.model_dump() for h in hits]}
                t_gen = time.perf_counter()
                second: GenerationOutcome | None = None
                for event, payload in self._stream_round(question, hits):
                    if event == "outcome":
                        second = payload
                    else:
                        yield event, payload
                generate_ms += _ms(time.perf_counter() - t_gen)
                assert second is not None
                if not second.spec.refused:
                    outcome = second
                else:
                    hits = first_hits  # 权威结果仍是首轮拒答，命中集跟着回退，保持自洽

        yield "done", self._summarize(
            question, hits, outcome.spec, outcome.parse_mode, retrieve_ms, generate_ms, retried
        ).model_dump()

    def _stream_round(self, question: str, hits: list[Hit]) -> Iterator[tuple[str, object]]:
        """一轮流式生成：转发 delta/retry，最后一项为 ("outcome", GenerationOutcome)。"""
        for item in self.generator.generate_stream(question, hits):
            if item.kind == "delta":
                yield "delta", {"text": item.text}
            elif item.kind == "retry":
                yield "retry", {"message": "输出格式异常，正在重试"}
            else:
                yield "outcome", item.outcome

    @staticmethod
    def _summarize(question: str, hits: list[Hit], spec: AnswerSpec, parse_mode: str,
                   retrieve_ms: int, generate_ms: int, retried: bool = False) -> AskResponse:
        by_index = {h.index: h for h in hits}
        cited = [by_index[i] for i in spec.citations if i in by_index]
        return AskResponse(
            question=question,
            answer=spec.answer,
            refused=spec.refused,
            retried=retried,
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
    from pipeline.config import get_settings

    from .retriever import get_retriever

    return RagService(
        get_retriever(), LLMGenerator.from_settings(), retry_k=get_settings().retry_k
    )