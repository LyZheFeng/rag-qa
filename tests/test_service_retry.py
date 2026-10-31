"""误拒兜底（v0.7 retry_k）单测：首次拒→二次答出 / 两次都拒 / 关闭 / 无新资料。

全部离线：mock retriever（按 k 截断）与 generator（按脚本逐次返回），不碰 chroma/LLM。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.generator import StreamItem
from app.schemas import AnswerSpec, Hit
from app.service import RETRY_MESSAGE, REWRITE_MESSAGE, RagService


def hits(n: int) -> list[Hit]:
    return [
        Hit(
            index=i,
            chunk_id=f"tutorial.body#{i:04d}",
            doc_name="tutorial/body.md",
            section_path=f"第{i}节",
            text=f"内容{i}",
            score=round(0.9 - i * 0.01, 4),
        )
        for i in range(1, n + 1)
    ]


class TopKRetriever:
    """模拟真实 top-k：从池子里截前 k 条，并记录每次调用的 k。"""

    def __init__(self, pool: list[Hit]):
        self.pool = pool
        self.calls: list[int] = []

    def retrieve(self, question: str, k: int = 5) -> list[Hit]:
        self.calls.append(k)
        return self.pool[:k]


class ScriptedGenerator:
    """第 n 次 generate 返回第 n 个脚本结果；记录每次喂进去的命中数。"""

    def __init__(self, specs: list[AnswerSpec]):
        self.specs = list(specs)
        self.calls: list[int] = []

    def generate(self, question: str, hits: list[Hit]):
        self.calls.append(len(hits))
        spec = self.specs.pop(0)
        return SimpleNamespace(spec=spec, parse_mode="json", raw="")


class ScriptedStreamGenerator:
    """流式替身：每轮先发一个 delta，再发 outcome；轮次由脚本决定。"""

    def __init__(self, specs: list[AnswerSpec]):
        self.specs = list(specs)
        self.calls: list[int] = []

    def generate_stream(self, question: str, hits: list[Hit]):
        self.calls.append(len(hits))
        spec = self.specs.pop(0)
        yield StreamItem("delta", text=spec.answer)
        yield StreamItem(
            "outcome", outcome=SimpleNamespace(spec=spec, parse_mode="json", raw="")
        )


REFUSE_1 = AnswerSpec(answer="第一轮：资料不足", citations=[], refused=True)
REFUSE_2 = AnswerSpec(answer="第二轮：仍不足", citations=[], refused=True)
ANSWER_2 = AnswerSpec(answer="用 BaseModel 声明请求体[2]", citations=[2], refused=False)


# ---------- 非流式 ask ----------


def test_first_refused_then_answered_returns_second_result():
    pool = hits(20)
    retriever = TopKRetriever(pool)
    gen = ScriptedGenerator([REFUSE_1, ANSWER_2])
    svc = RagService(retriever, gen, retry_k=20)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5, 20]  # 首次 k，拒答后按 retry_k 复查
    assert gen.calls == [5, 20]
    assert resp.retried is True
    assert resp.refused is False
    assert resp.answer == ANSWER_2.answer
    assert resp.retrieved == pool  # 终态用扩大后的命中集
    assert [h.index for h in resp.cited] == [2]
    assert resp.latency.total_ms >= resp.latency.retrieve_ms + resp.latency.generate_ms - 1


def test_both_refused_keeps_first_refusal():
    pool = hits(20)
    retriever = TopKRetriever(pool)
    gen = ScriptedGenerator([REFUSE_1, REFUSE_2])
    svc = RagService(retriever, gen, retry_k=20)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5, 20]
    assert gen.calls == [5, 20]  # 二次确实重答了
    assert resp.retried is True
    assert resp.refused is True
    assert resp.answer == REFUSE_1.answer  # 权威结果仍是首轮拒答
    assert len(resp.retrieved) == 5  # 命中集跟着首轮结果，保持自洽


def test_retry_k_zero_disables_second_attempt():
    retriever = TopKRetriever(hits(20))
    gen = ScriptedGenerator([REFUSE_1])
    svc = RagService(retriever, gen, retry_k=0)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5]
    assert gen.calls == [5]
    assert resp.retried is False
    assert resp.refused is True


def test_retry_skipped_when_retrieval_finds_no_more_context():
    retriever = TopKRetriever(hits(5))  # 池子只有 5 条，k=20 也拿不到更多
    gen = ScriptedGenerator([REFUSE_1])
    svc = RagService(retriever, gen, retry_k=20)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5, 20]  # 复查过
    assert gen.calls == [5]  # 但没白烧第二次生成
    assert resp.retried is False
    assert resp.refused is True


def test_retry_k_not_deeper_than_k_disables_second_attempt():
    retriever = TopKRetriever(hits(20))
    gen = ScriptedGenerator([REFUSE_1])
    svc = RagService(retriever, gen, retry_k=5)  # 不深于首轮 k

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5]
    assert resp.retried is False


def test_first_round_answer_does_not_retrieve_again():
    retriever = TopKRetriever(hits(20))
    gen = ScriptedGenerator([ANSWER_2])
    svc = RagService(retriever, gen, retry_k=20)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5]
    assert resp.retried is False
    assert resp.refused is False


# ---------- 流式 ask_stream ----------


def _names(events):
    return [e for e, _ in events]


def test_stream_refusal_retry_event_order_and_done():
    pool = hits(20)
    gen = ScriptedStreamGenerator([REFUSE_1, ANSWER_2])
    svc = RagService(TopKRetriever(pool), gen, retry_k=20)

    events = list(svc.ask_stream("如何声明请求体", k=5))

    assert _names(events) == ["sources", "delta", "retry", "sources", "delta", "done"]
    sources = [p for e, p in events if e == "sources"]
    assert [len(s["hits"]) for s in sources] == [5, 20]  # 二次命中集扩大
    assert events[2][1]["message"] == RETRY_MESSAGE  # retry 让前端清屏
    done = events[-1][1]
    assert done["retried"] is True
    assert done["refused"] is False
    assert done["answer"] == ANSWER_2.answer
    assert len(done["retrieved"]) == 20
    assert [h["index"] for h in done["cited"]] == [2]


def test_stream_both_refused_keeps_first_result():
    gen = ScriptedStreamGenerator([REFUSE_1, REFUSE_2])
    svc = RagService(TopKRetriever(hits(20)), gen, retry_k=20)

    events = list(svc.ask_stream("如何声明请求体", k=5))

    assert _names(events) == ["sources", "delta", "retry", "sources", "delta", "done"]
    done = events[-1][1]
    assert done["retried"] is True
    assert done["refused"] is True
    assert done["answer"] == REFUSE_1.answer
    assert len(done["retrieved"]) == 5


def test_stream_happy_path_has_no_retry_event():
    gen = ScriptedStreamGenerator([ANSWER_2])
    svc = RagService(TopKRetriever(hits(20)), gen, retry_k=20)

    events = list(svc.ask_stream("如何声明请求体", k=5))

    assert _names(events) == ["sources", "delta", "done"]
    assert events[-1][1]["retried"] is False


def test_stream_retry_k_zero_disables_second_attempt():
    gen = ScriptedStreamGenerator([REFUSE_1])
    svc = RagService(TopKRetriever(hits(20)), gen, retry_k=0)

    events = list(svc.ask_stream("如何声明请求体", k=5))

    assert _names(events) == ["sources", "delta", "done"]
    assert events[-1][1]["retried"] is False
    assert events[-1][1]["refused"] is True


# ---------- API 层：SSE 帧序与响应契约（不经过真实检索/LLM） ----------


def parse_sse(text: str) -> list[tuple[str, dict]]:
    import json as _json

    frames = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        frames.append((lines[0][len("event: "):], _json.loads(lines[1][len("data: "):])))
    return frames


def test_api_stream_retry_frames():
    from app.api import app
    from fastapi.testclient import TestClient

    gen = ScriptedStreamGenerator([REFUSE_1, ANSWER_2])
    app.state.service = RagService(TopKRetriever(hits(20)), gen, retry_k=20)

    r = TestClient(app).get("/ask/stream", params={"q": "如何声明请求体"})

    assert r.status_code == 200
    frames = parse_sse(r.text)
    assert [e for e, _ in frames] == ["sources", "delta", "retry", "sources", "delta", "done"]
    assert [len(p["hits"]) for e, p in frames if e == "sources"] == [5, 20]
    assert frames[2][1]["message"] == RETRY_MESSAGE
    done = frames[-1][1]
    assert done["retried"] is True
    assert done["refused"] is False
    assert done["answer"] == ANSWER_2.answer


def test_api_ask_exposes_retried_flag():
    from app.api import app
    from fastapi.testclient import TestClient

    gen = ScriptedGenerator([REFUSE_1, ANSWER_2])
    app.state.service = RagService(TopKRetriever(hits(20)), gen, retry_k=20)

    body = TestClient(app).post("/ask", json={"question": "如何声明请求体"}).json()

    assert body["retried"] is True
    assert body["refused"] is False
    assert len(body["retrieved"]) == 20


# ---------- 定向改写兜底（v0.9 实验开关，默认关） ----------


class RoutingRetriever:
    """按 query 返回不同命中（模拟改写后检索到新资料），记录每次 (query, k)。"""

    def __init__(self, by_query: dict[str, list[Hit]]):
        self.by_query = by_query
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, question: str, k: int = 5) -> list[Hit]:
        self.calls.append((question, k))
        return self.by_query.get(question, [])[:k]


class RewriteGenerator(ScriptedGenerator):
    def __init__(self, specs: list[AnswerSpec], rewritten: str):
        super().__init__(specs)
        self.rewritten = rewritten

    def rewrite_query(self, question: str) -> str:
        return self.rewritten


class StreamRewriteGenerator(ScriptedStreamGenerator):
    def __init__(self, specs: list[AnswerSpec], rewritten: str):
        super().__init__(specs)
        self.rewritten = rewritten

    def rewrite_query(self, question: str) -> str:
        return self.rewritten


Q1 = "如何声明请求体"
Q2 = "FastAPI 用 BaseModel 声明请求体 Request Body"


def test_ask_rewrite_stage_answers_when_rewrite_finds_more():
    pool = hits(20)
    retriever = RoutingRetriever({Q1: pool, Q2: pool})
    gen = RewriteGenerator([REFUSE_1, REFUSE_2, ANSWER_2], rewritten=Q2)
    svc = RagService(retriever, gen, retry_k=20, retry_rewrite=True)

    resp = svc.ask(Q1, k=5)

    assert [c[0] for c in retriever.calls] == [Q1, Q1, Q2]
    assert [c[1] for c in retriever.calls] == [5, 20, 20]
    assert gen.calls == [5, 20, 10]  # 首轮 5、二次 20、改写合并 10
    assert resp.retried is True and resp.rewritten is True
    assert resp.refused is False
    assert resp.answer == ANSWER_2.answer
    # 合并集重排 1..N，引用 [2] 落在第二段
    assert resp.retrieved[1].chunk_id == pool[1].chunk_id
    assert [h.index for h in resp.retrieved] == list(range(1, len(resp.retrieved) + 1))
    assert resp.cited[0].chunk_id == pool[1].chunk_id


def test_rewrite_disabled_by_default():
    pool = hits(20)
    retriever = RoutingRetriever({Q1: pool, Q2: pool})
    gen = RewriteGenerator([REFUSE_1, REFUSE_2], rewritten=Q2)
    svc = RagService(retriever, gen, retry_k=20)  # retry_rewrite 默认 False

    resp = svc.ask(Q1, k=5)

    assert [c[0] for c in retriever.calls] == [Q1, Q1]
    assert resp.rewritten is False
    assert resp.refused is True


def test_rewrite_skipped_when_query_unchanged():
    pool = hits(20)
    retriever = RoutingRetriever({Q1: pool})
    gen = RewriteGenerator([REFUSE_1, REFUSE_2], rewritten=Q1)  # 改写没变化
    svc = RagService(retriever, gen, retry_k=20, retry_rewrite=True)

    resp = svc.ask(Q1, k=5)

    assert [c[0] for c in retriever.calls] == [Q1, Q1]
    assert resp.rewritten is False
    assert resp.refused is True


def test_rewrite_failure_is_skipped():
    class BoomRewriteGenerator(RewriteGenerator):
        def rewrite_query(self, question: str) -> str:
            raise RuntimeError("LLM 断连")

    pool = hits(20)
    retriever = RoutingRetriever({Q1: pool})
    gen = BoomRewriteGenerator([REFUSE_1, REFUSE_2], rewritten=Q2)
    svc = RagService(retriever, gen, retry_k=20, retry_rewrite=True)

    resp = svc.ask(Q1, k=5)  # 不抛异常，按首轮拒答返回

    assert resp.rewritten is False
    assert resp.refused is True


def test_stream_rewrite_stage_event_order():
    pool = hits(20)
    retriever = RoutingRetriever({Q1: pool, Q2: pool})
    gen = StreamRewriteGenerator([REFUSE_1, REFUSE_2, ANSWER_2], rewritten=Q2)
    svc = RagService(retriever, gen, retry_k=20, retry_rewrite=True)

    events = list(svc.ask_stream(Q1, k=5))

    assert _names(events) == [
        "sources", "delta", "retry", "sources", "delta", "retry", "sources", "delta", "done"
    ]
    assert events[5][1]["message"] == REWRITE_MESSAGE
    done = events[-1][1]
    assert done["retried"] is True and done["rewritten"] is True
    assert done["refused"] is False


def test_merge_hits_dedupes_and_renumbers():
    from app.service import _has_new, _merge_hits

    primary, secondary = hits(3), hits(5)
    merged = _merge_hits(primary, secondary, 4)
    assert [h.index for h in merged] == [1, 2, 3, 4]
    assert [h.chunk_id for h in merged] == [h.chunk_id for h in primary] + [secondary[3].chunk_id]
    assert _has_new(merged, primary) is True
    assert _has_new(primary, primary) is False


# ---------- 首轮检索深度（v0.10 top_k） ----------


def test_default_k_used_when_not_given():
    retriever = TopKRetriever(hits(20))
    gen = ScriptedGenerator([ANSWER_2])
    svc = RagService(retriever, gen, retry_k=20, default_k=8)

    resp = svc.ask("如何声明请求体")

    assert retriever.calls == [8]
    assert gen.calls == [8]
    assert len(resp.retrieved) == 8


def test_explicit_k_overrides_default():
    retriever = TopKRetriever(hits(20))
    gen = ScriptedGenerator([ANSWER_2])
    svc = RagService(retriever, gen, retry_k=20, default_k=8)

    resp = svc.ask("如何声明请求体", k=5)

    assert retriever.calls == [5]
    assert len(resp.retrieved) == 5