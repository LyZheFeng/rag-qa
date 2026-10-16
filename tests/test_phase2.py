"""Phase 2 单测：上下文构建 / JSON 抽取 / 引用校验 / 重试降级 / 编排 / API（全部无网络）。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import __version__
from app.api import app
from app.generator import LLMGenerator, build_context, extract_json, validate_citations
from app.schemas import AnswerSpec, AskResponse, Hit
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


# ---------- extract_json ----------


def test_extract_json_plain():
    assert extract_json('{"answer": "a", "citations": [1], "refused": false}') == {
        "answer": "a",
        "citations": [1],
        "refused": False,
    }


def test_extract_json_fenced_with_prose():
    text = '好的，以下是答案：\n```json\n{"answer": "a", "citations": [], "refused": true}\n```\n希望有帮助'
    assert extract_json(text)["refused"] is True


def test_extract_json_think_tag():
    text = "<think>推理过程</think>{\"answer\": \"a\"}"
    assert extract_json(text) == {"answer": "a"}


def test_extract_json_garbage_returns_none():
    assert extract_json("这个问题我无法回答") is None
    assert extract_json("[1, 2]") is None
    assert extract_json('"字符串"') is None


# ---------- validate_citations ----------


def test_validate_citations_range_dedupe_sort():
    assert validate_citations([3, 1, 3, 9, 0, -1, 2], k=5) == [1, 2, 3]


def test_validate_citations_bool_excluded():
    assert validate_citations([True, 1], k=5) == [1]


# ---------- build_context ----------


def test_build_context_numbered_with_source():
    ctx = build_context([hit(1, "请求体用 Pydantic 模型"), hit(2, "class Item(BaseModel):")])
    assert "[1] 来源：tutorial/body.md > 请求体" in ctx
    assert "[2] 来源：" in ctx
    assert "请求体用 Pydantic 模型" in ctx


# ---------- LLMGenerator 重试与降级 ----------


class FakeClient:
    """按脚本依次回话，记录调用。"""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[dict] = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kw):
        self.calls.append(kw)
        content = self._replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def make_gen(replies: list[str]) -> tuple[LLMGenerator, FakeClient]:
    client = FakeClient(replies)
    return LLMGenerator(client, "fake-model"), client


def test_generator_json_first_try():
    gen, client = make_gen(['{"answer": "用 BaseModel", "citations": [1], "refused": false}'])
    out = gen.generate("如何声明请求体", [hit(1), hit(2)])
    assert out.parse_mode == "json"
    assert out.spec.citations == [1]
    assert len(client.calls) == 1


def test_generator_retry_success():
    gen, client = make_gen(
        [
            "答案：用 BaseModel 声明",  # 首次非 JSON
            '{"answer": "用 BaseModel", "citations": [2], "refused": false}',
        ]
    )
    out = gen.generate("如何声明请求体", [hit(1), hit(2)])
    assert out.parse_mode == "retry"
    assert out.spec.citations == [2]
    assert len(client.calls) == 2
    # 重试消息携带了首轮对话
    assert client.calls[1]["messages"][-2]["role"] == "assistant"
    assert client.calls[1]["messages"][-1]["role"] == "user"


def test_generator_fallback_safe_refusal():
    """两次解析失败 → 安全拒答：不再把原文当答案（可能夹带围栏/思维链）。"""
    gen, client = make_gen(["纯文本回答一", "纯文本回答二"])
    out = gen.generate("如何声明请求体", [hit(1), hit(2)])
    assert out.parse_mode == "fallback"
    assert out.spec.refused is True
    assert out.spec.citations == []
    assert "格式异常" in out.spec.answer
    assert "纯文本回答二" not in out.spec.answer


def test_generator_citation_sanitized():
    gen, _ = make_gen(['{"answer": "a", "citations": [7, 2, 2, true], "refused": false}'])
    out = gen.generate("q", [hit(1), hit(2)])
    assert out.spec.citations == [2]


def test_generator_refused_clears_citations():
    gen, _ = make_gen(['{"answer": "文档未涵盖", "citations": [1], "refused": true}'])
    out = gen.generate("q", [hit(1)])
    assert out.spec.refused is True
    assert out.spec.citations == []


# ---------- RagService 编排 ----------


class FakeRetriever:
    def __init__(self, hits):
        self._hits = hits
        self.collection = SimpleNamespace(count=lambda: 1701)
        self.embedder = SimpleNamespace(dim=1024)

    def retrieve(self, query: str, k: int = 5):
        return self._hits[:k]


class FakeGenerator:
    def __init__(self, spec: AnswerSpec, parse_mode: str = "json", client=None):
        self._spec = spec
        self.parse_mode = parse_mode
        self.model = "fake-model"
        self.client = client  # /ready 的 LLM 探活走 generator.client
        self.calls = []

    def generate(self, question, hits):
        self.calls.append((question, len(hits)))
        return SimpleNamespace(spec=self._spec, parse_mode=self.parse_mode, raw="raw")


class FakeLLMClient:
    """openai 客户端替身:with_options().models.list() 按构造参数成败。"""

    def __init__(self, ok: bool = True):
        self.ok = ok

    def with_options(self, **kw):
        return self

    @property
    def models(self):
        return self

    def list(self):
        if not self.ok:
            raise RuntimeError("connection refused")
        return []


def test_service_ask_enriches_citations():
    h1, h2 = hit(1), hit(2)
    svc = RagService(FakeRetriever([h1, h2]), FakeGenerator(AnswerSpec(answer="A[2]", citations=[2])))
    resp = svc.ask("如何声明请求体")
    assert isinstance(resp, AskResponse)
    assert resp.cited == [h2]
    assert resp.retrieved == [h1, h2]
    assert resp.latency.total_ms >= resp.latency.retrieve_ms + resp.latency.generate_ms - 1


def test_service_ask_empty_hits_refuses():
    svc = RagService(FakeRetriever([]), FakeGenerator(AnswerSpec(answer="x")))
    resp = svc.ask("任何问题")
    assert resp.refused is True
    assert resp.cited == []


# ---------- FastAPI ----------


def test_api_ask_with_fake_service():
    h1 = hit(1)
    svc = RagService(FakeRetriever([h1]), FakeGenerator(AnswerSpec(answer="用 BaseModel [1]", citations=[1])))
    app.state.service = svc  # 不进 with：lifespan 不跑，fake 不被覆盖
    client = TestClient(app)
    r = client.post("/ask", json={"question": "如何声明请求体"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "用 BaseModel [1]"
    assert body["cited"][0]["chunk_id"] == "tutorial.body#0001"
    assert body["parse_mode"] == "json"

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["chunks"] == 1701
    assert r.json()["version"] == __version__


def test_api_ready_llm_up_and_down():
    from app.api import app as _app

    h1 = hit(1)
    ok_svc = RagService(FakeRetriever([h1]), FakeGenerator(AnswerSpec(answer="x"), client=FakeLLMClient(ok=True)))
    _app.state.service = ok_svc
    client = TestClient(_app)
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "vector_ready": True, "llm_ready": True}

    down_svc = RagService(FakeRetriever([h1]), FakeGenerator(AnswerSpec(answer="x"), client=FakeLLMClient(ok=False)))
    _app.state.service = down_svc
    r = client.get("/ready")
    assert r.status_code == 503
    body = r.json()["detail"]
    assert body["llm_ready"] is False
    assert body["vector_ready"] is True  # 向量侧不受 LLM 断连影响


def test_api_ready_no_llm_client_marks_not_ready():
    # generator 没挂 client(如异常构造)时,/ready 不炸,按未就绪处理
    app.state.service = RagService(FakeRetriever([hit(1)]), FakeGenerator(AnswerSpec(answer="x")))
    r = TestClient(app).get("/ready")
    assert r.status_code == 503
    assert r.json()["detail"]["llm_ready"] is False


def test_api_ask_rejected_when_saturated():
    from app.api import MAX_CONCURRENT_ASKS, _ask_semaphore

    app.state.service = RagService(FakeRetriever([hit(1)]), FakeGenerator(AnswerSpec(answer="x")))
    client = TestClient(app)
    acquired = []
    try:
        for _ in range(MAX_CONCURRENT_ASKS):
            _ask_semaphore.acquire(blocking=False)
            acquired.append(True)
        r = client.post("/ask", json={"question": "并发打满时"})
        assert r.status_code == 503
        assert r.json()["detail"] == "服务繁忙，请稍后重试"
    finally:
        for _ in acquired:
            _ask_semaphore.release()


def test_api_ask_validation_error():
    app.state.service = RagService(FakeRetriever([]), FakeGenerator(AnswerSpec(answer="x")))
    client = TestClient(app)
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "q", "k": 99}).status_code == 422


def test_api_ask_error_sanitized():
    """下游异常 → 502 脱敏：客户端只见固定文案+追踪 id，不见异常细节。"""

    class BoomService:
        retriever = FakeRetriever([])

        def ask(self, question, k=5):
            raise RuntimeError("内网 vLLM 连接被拒绝: http://vllm.internal:8000 secret-detail")

    app.state.service = BoomService()
    client = TestClient(app)
    r = client.post("/ask", json={"question": "任何问题"})
    assert r.status_code == 502
    body = r.json()["detail"]
    assert body["message"] == "生成服务暂时不可用"
    assert body["trace_id"]  # 有追踪 id 可回查服务端日志
    assert "RuntimeError" not in r.text and "secret-detail" not in r.text
