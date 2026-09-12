"""FastAPI 服务：POST /ask 问答 + GET /health（存活）+ GET /ready（就绪）。

启动（仓库根）：uvicorn app.api:app --port 8000
- /health 便宜（不碰 LLM），存活探针用
- /ready 会 ping LLM（3s 超时），向量与 LLM 都就绪才 200，编排就绪探针用
"""

from __future__ import annotations

import logging
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # streamlit/uvicorn 任意 cwd 下可 import

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pipeline.config import get_settings
    from pipeline.manifest import check_manifest

    s = get_settings()
    state, msg, manifest = check_manifest(s.chroma_dir, s.chunks_path, collection=s.collection)
    if state == "mismatch":
        raise RuntimeError(f"索引版本校验失败：{msg}")  # 启动即失败，不放行错配索引
    if state == "missing":
        logger.warning("索引校验跳过：%s", msg)

    service = get_service()  # 启动即预热嵌入模型，首问不付 2.4s
    app.state.service = service
    core = _vector_core(service)
    if state == "ok" and core is not None and s.retriever != "parentchild":
        actual, expected = core.collection.count(), manifest.get("chunk_count")
        if actual != expected:
            raise RuntimeError(f"索引版本校验失败：Chroma 条数 {actual} 与 manifest {expected} 不一致")
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
            client.with_options(timeout=LLM_PING_TIMEOUT).models.list()
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
