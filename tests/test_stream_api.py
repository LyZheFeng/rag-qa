"""流式接口单测：SSE 帧格式 / 事件序 / 增量 JSON 前缀抽取 / 拒答 / 错误 / 忙路（全部无网络）。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import MAX_CONCURRENT_ASKS, _ask_semaphore, app
from app.generator import GenerationOutcome, LLMGenerator, scan_answer
from app.schemas import AnswerSpec, Hit
from app.service import RagService
from fastapi.testclient import TestClient


def hit(i: int, text: str = "内容") -> Hit:
    return Hit(
        index=i,
        chunk_id=f"tutorial.body#{i:04d}",
        doc_name="tutorial/body.md",
        section_path="请求体",
        text=text,
        score=0.8,
    )


# ---------- scan_answer（半成品 JSON 的 answer 前缀抽取） ----------


def test_scan_answer_plain_prefix():
    # complete 指 answer 字符串已见闭合引号（此后不会再有增量），不是整个 JSON 闭合
    assert scan_answer('{"answer": "FastAPI 是", "citations": [1]') == ("FastAPI 是", True)
    assert scan_answer('{"answer": "FastAPI 是') == ("FastAPI 是", False)  # 字符串未闭合
    assert scan_answer('{"answer": "FastAPI 是", "citations": [1]}') == ("FastAPI 是", True)


def test_scan_answer_decodes_escapes_incrementally():
    # 换行/unicode 转义按已解码文本下发；尾部不完整转义先砍掉
    assert scan_answer('{"answer": "a\\nb\\u4e2d') == ("a\nb中", False)
    assert scan_answer('{"answer": "a\\nb\\u4e2d\\') == ("a\nb中", False)  # 尾部孤立反斜杠
    assert scan_answer('{"answer": "a\\"q\\""}') == ('a"q"', True)


def test_scan_answer_tolerates_think_and_fence():
    assert scan_answer('<think>x {"answer": "伪"}</think>{"answer": "真值"') == ("真值", True)


def test_scan_answer_ignores_nested_and_string_occurrences():
    # "answer" 出现在别的字符串值里、或嵌套对象里，都不能误命中
    buf = '{"note": "the \\"answer\\" key", "meta": {"answer": "嵌套"}, "answer": "顶层值"'
    assert scan_answer(buf) == ("顶层值", True)


def test_scan_answer_missing_returns_none():
    assert scan_answer("还在思考，没有 JSON") is None
    assert scan_answer('{"refused": true') is None


# ---------- 假件：流式 LLM 按 token 切片吐 JSON ----------


class FakeStreamGenerator(LLMGenerator):
    """把完整 JSON 文本按 7 字符一片吐出，模拟 token 流。"""

    def __init__(self, chunks: list[str]):
        super().__init__(client=None, model="fake")
        self.chunks = chunks  # 每个元素是一次完整尝试的原始输出

    def _chat_stream(self, messages):
        for i in range(0, len(self.chunks[0]), 7):
            yield self.chunks[0][i : i + 7]

    # generate() 不在流式链路上，给个占位避免误用
    def generate(self, question, hits):  # pragma: no cover
        raise AssertionError("流式链路不应调用 generate()")


class RetryOnceGenerator(FakeStreamGenerator):
    """首次输出不可解析，重试一次成功——验证 retry 事件与前端清空语义。"""

    def __init__(self, chunks: list[str]):
        super().__init__(chunks)
        self.calls = 0

    def _chat_stream(self, messages):
        text = self.chunks[self.calls]  # 第 1 次吐坏输出，第 2 次（重试）吐好输出
        self.calls += 1
        for i in range(0, len(text), 7):
            yield text[i : i + 7]


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, question, k=5):
        return self.hits


def parse_sse(text: str) -> list[tuple[str, dict]]:
    import json as _json

    frames = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        event = lines[0][len("event: ") :]
        frames.append((event, _json.loads(lines[1][len("data: ") :])))
    return frames


def ok_json(answer: str, cites: list[int]) -> str:
    import json as _json

    return _json.dumps({"answer": answer, "citations": cites, "refused": False}, ensure_ascii=False)


# ---------- API：事件序与帧格式 ----------


def test_stream_happy_path_event_order_and_frames():
    gen = FakeStreamGenerator([ok_json("答案是甲[1] 也是乙[2]", [1, 2])])
    app.state.service = RagService(FakeRetriever([hit(1), hit(2)]), gen)
    r = TestClient(app).get("/ask/stream", params={"q": "甲和乙是什么"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = parse_sse(r.text)
    names = [e for e, _ in frames]
    assert names[0] == "sources" and names[-1] == "done"
    assert "delta" in names and "retry" not in names and "error" not in names
    assert frames[0][1]["hits"][0]["index"] == 1
    streamed = "".join(p["text"] for e, p in frames if e == "delta")
    assert streamed == "答案是甲[1] 也是乙[2]"  # 前缀增量拼回 == 完整 answer
    done = frames[-1][1]
    assert done["answer"] == "答案是甲[1] 也是乙[2]"
    assert done["refused"] is False and done["parse_mode"] == "json"
    assert [h["index"] for h in done["cited"]] == [1, 2]
    assert set(done["latency"]) == {"retrieve_ms", "generate_ms", "total_ms"}


def test_stream_refusal_without_hits():
    gen = FakeStreamGenerator([ok_json("x", [])])
    app.state.service = RagService(FakeRetriever([]), gen)
    frames = parse_sse(TestClient(app).get("/ask/stream", params={"q": "检索不到的问题"}).text)
    assert [e for e, _ in frames] == ["sources", "done"]
    assert frames[0][1]["hits"] == []
    assert frames[-1][1]["refused"] is True


def test_stream_retry_path_replaces_display():
    gen = RetryOnceGenerator(["不是 JSON 的第一次输出", ok_json("重试后的答案", [])])
    app.state.service = RagService(FakeRetriever([hit(1)]), gen)
    frames = parse_sse(TestClient(app).get("/ask/stream", params={"q": "问个问题"}).text)
    names = [e for e, _ in frames]
    assert names[0] == "sources" and names[-1] == "done"
    assert names.count("retry") == 1  # 前端收到 retry 应清空已显示的临时文本
    assert frames[-1][1]["parse_mode"] == "retry"


def test_stream_llm_failure_yields_error_event():
    class BoomGenerator(FakeStreamGenerator):
        def _chat_stream(self, messages):
            raise RuntimeError("vLLM 断连")
            yield  # pragma: no cover

    app.state.service = RagService(FakeRetriever([hit(1)]), BoomGenerator(["x"]))
    frames = parse_sse(TestClient(app).get("/ask/stream", params={"q": "问个问题"}).text)
    assert frames[-1][0] == "error"
    assert "trace_id" in frames[-1][1]


def test_stream_busy_yields_error_event():
    gen = FakeStreamGenerator([ok_json("a", [])])
    app.state.service = RagService(FakeRetriever([hit(1)]), gen)
    for _ in range(MAX_CONCURRENT_ASKS):
        _ask_semaphore.acquire(blocking=False)
    try:
        frames = parse_sse(TestClient(app).get("/ask/stream", params={"q": "问个问题"}).text)
        assert frames == [("error", {"message": "服务繁忙，请稍后重试"})]
    finally:
        for _ in range(MAX_CONCURRENT_ASKS):
            _ask_semaphore.release()


def test_stream_query_validation():
    client = TestClient(app)
    assert client.get("/ask/stream", params={"q": "短"}).status_code == 422
    assert client.get("/ask/stream", params={"q": "合法问题", "k": 11}).status_code == 422


def test_stream_semaphore_released_after_stream():
    gen = FakeStreamGenerator([ok_json("a", [])])
    app.state.service = RagService(FakeRetriever([hit(1)]), gen)
    TestClient(app).get("/ask/stream", params={"q": "问个问题"})
    # 流结束后信号量应全额可用
    for _ in range(MAX_CONCURRENT_ASKS):
        assert _ask_semaphore.acquire(blocking=False)
    for _ in range(MAX_CONCURRENT_ASKS):
        _ask_semaphore.release()


# ---------- service 层直测（不经 HTTP） ----------


def test_service_ask_stream_yields_sources_then_done():
    gen = FakeStreamGenerator([ok_json("答案", [1])])
    svc = RagService(FakeRetriever([hit(1)]), gen)
    events = list(svc.ask_stream("问题", k=5))
    assert events[0][0] == "sources"
    assert events[-1][0] == "done" and events[-1][1]["answer"] == "答案"
