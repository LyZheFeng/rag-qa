"""FastAPI 服务：POST /ask 问答 + GET /ask/stream（SSE 流式）+ GET /health（存活）+ GET /ready（就绪）。

启动（仓库根）：uvicorn app.api:app --port 8000
- /health 便宜（不碰 LLM），存活探针用
- /ready 会 ping LLM（3s 超时），向量与 LLM 都就绪才 200，编排就绪探针用
- /ask/stream 事件序：sources（检索完成）→ delta*（临时增量）→ [retry → delta*]* → done（权威终态）
  错误一律收拢为 error 事件（含 trace_id），流以 done/error 收尾
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # uvicorn/pytest 任意 cwd 下可 import

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import __version__
from .schemas import AskRequest, AskResponse
from .service import RagService, get_service

# 挂到 uvicorn 的错误日志通道：不用额外配置就能在服务端控制台看到启动横幅与完整异常
logger = logging.getLogger("uvicorn.error")

# 同步链路（embedding + LLM）放进线程池跑，不占事件循环；超出并发的请求直接 503
LLM_PING_TIMEOUT = 3.0
MAX_CONCURRENT_ASKS = 4
_ask_semaphore = threading.Semaphore(MAX_CONCURRENT_ASKS)


def _vector_core(svc: RagService):
    """沿包装链下钻到 VectorRetriever（vector/base/child 三种包装名），找不到返回 None。"""
    r = svc.retriever
    while r is not None and not hasattr(r, "collection"):
        r = getattr(r, "vector", None) or getattr(r, "base", None) or getattr(r, "child", None)
    return r


def _cors_origins() -> str:
    from pipeline.config import get_settings

    return get_settings().cors_origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pipeline.config import get_settings

    # get_service → get_retriever 内做索引 manifest 校验(错配在嵌入模型加载前 fail-fast)
    service = get_service()
    app.state.service = service
    s = get_settings()
    core = _vector_core(service)
    if core is not None:
        logger.info(
            "rag-qa v%s 就绪 | retriever=%s | embed=%s (%s, dim=%s) | collection=%s | chunks=%s | llm=%s",
            __version__,
            type(service.retriever).__name__,
            s.embed_model,
            type(core.embedder).__name__,
            getattr(core.embedder, "dim", "?"),
            getattr(core.collection, "name", "?"),
            core.collection.count(),
            service.generator.model,
        )
    else:
        logger.warning("rag-qa 就绪，但未能定位底层向量检索器（retriever=%s）", type(service.retriever).__name__)
    yield


app = FastAPI(title="rag-qa", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins().split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _svc(request: Request) -> RagService:
    return getattr(request.app.state, "service", None) or get_service()


@app.get("/health")
def health(request: Request) -> dict:
    """存活检查：只看本地组件（向量库/嵌入），不碰 LLM，响应快。"""
    svc = _svc(request)
    core = _vector_core(svc)
    if core is None:
        raise HTTPException(status_code=500, detail="无法定位底层向量检索器")
    return {
        "status": "ok",
        "version": __version__,
        "retriever": type(svc.retriever).__name__,
        "chunks": core.collection.count(),
        "embed_dim": core.embedder.dim,
        "llm_model": svc.generator.model,
    }


@app.get("/ready")
async def ready(request: Request) -> dict:
    """就绪检查：向量库有数据 + LLM 可连才 200，否则 503。"""
    svc = _svc(request)
    core = _vector_core(svc)
    vector_ready = core is not None and core.collection.count() > 0

    llm_ready = False
    client = getattr(svc.generator, "client", None)
    if client is not None:
        try:
            # 探活也放线程池:同步 client 超时会阻塞事件循环
            await run_in_threadpool(lambda: client.with_options(timeout=LLM_PING_TIMEOUT).models.list())
            llm_ready = True
        except Exception as e:  # 细节只进服务端日志
            logger.warning("ready 检查：LLM 不通 %s: %s", type(e).__name__, e)

    body = {"status": "ready" if (vector_ready and llm_ready) else "not_ready",
            "vector_ready": vector_ready, "llm_ready": llm_ready}
    if not (vector_ready and llm_ready):
        raise HTTPException(status_code=503, detail=body)
    return body


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request) -> AskResponse:
    if not _ask_semaphore.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="服务繁忙，请稍后重试")
    try:
        svc = _svc(request)
        return await run_in_threadpool(svc.ask, req.question, req.k)
    except Exception as e:  # vLLM 断连/超时等，统一 502
        trace_id = uuid.uuid4().hex[:12]
        logger.exception("ask 失败 trace_id=%s", trace_id)  # 完整异常只留服务端日志
        raise HTTPException(
            status_code=502,
            detail={"message": "生成服务暂时不可用", "trace_id": trace_id},
        ) from e
    finally:
        _ask_semaphore.release()


def _sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/ask/stream")
async def ask_stream(
    request: Request,
    q: str = Query(min_length=2, max_length=1000),
    k: int = Query(default=5, ge=1, le=10),
):
    svc = _svc(request)

    def guarded() -> Iterable[tuple[str, dict]]:
        # 信号量拿放都在同步生成器内：请求体未开始迭代就不占用；占用时长=整条流
        if not _ask_semaphore.acquire(blocking=False):
            yield "error", {"message": "服务繁忙，请稍后重试"}
            return
        try:
            yield from svc.ask_stream(q, k)
        finally:
            _ask_semaphore.release()

    async def sse():
        try:
            async for event, payload in iterate_in_threadpool(guarded()):
                yield _sse_frame(event, payload)
        except Exception as e:  # 与 /ask 同口径：细节进日志，前端只拿 trace_id
            trace_id = uuid.uuid4().hex[:12]
            logger.exception("ask/stream 失败 trace_id=%s", trace_id)
            yield _sse_frame("error", {"message": "生成服务暂时不可用", "trace_id": trace_id})

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
