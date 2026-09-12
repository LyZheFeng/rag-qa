"""FastAPI 服务：POST /ask 问答 + GET /health。

启动（仓库根）：uvicorn app.api:app --port 8000
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # streamlit/uvicorn 任意 cwd 下可 import

from fastapi import FastAPI, HTTPException, Request

from .schemas import AskRequest, AskResponse
from .service import RagService, get_service

# 挂到 uvicorn 的错误日志通道：不用额外配置就能在服务端控制台看到启动横幅与完整异常
logger = logging.getLogger("uvicorn.error")


def _vector_core(svc: RagService):
    """沿包装链下钻到 VectorRetriever（vector/base/child 三种包装名），找不到返回 None。"""
    r = svc.retriever
    while r is not None and not hasattr(r, "collection"):
        r = getattr(r, "vector", None) or getattr(r, "base", None) or getattr(r, "child", None)
    return r


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = get_service()  # 启动即预热嵌入模型，首问不付 2.4s
    app.state.service = service
    core = _vector_core(service)
    if core is not None:
        from pipeline.config import get_settings

        logger.info(
            "rag-qa 就绪 | retriever=%s | embed=%s (%s, dim=%s) | collection=%s | chunks=%s | llm=%s",
            type(service.retriever).__name__,
            get_settings().embed_model,
            type(core.embedder).__name__,
            getattr(core.embedder, "dim", "?"),
            getattr(core.collection, "name", "?"),
            core.collection.count(),
            service.generator.model,
        )
    else:
        logger.warning("rag-qa 就绪，但未能定位底层向量检索器（retriever=%s）", type(service.retriever).__name__)
    yield


app = FastAPI(title="rag-qa", version="0.1.0", lifespan=lifespan)


def _svc(request: Request) -> RagService:
    return getattr(request.app.state, "service", None) or get_service()


@app.get("/health")
def health(request: Request) -> dict:
    svc = _svc(request)
    core = _vector_core(svc)
    if core is None:
        raise HTTPException(status_code=500, detail="无法定位底层向量检索器")
    return {
        "status": "ok",
        "retriever": type(svc.retriever).__name__,
        "chunks": core.collection.count(),
        "embed_dim": core.embedder.dim,
        "llm_model": svc.generator.model,
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    try:
        return _svc(request).ask(req.question, k=req.k)
    except Exception as e:  # vLLM 断连/超时等，统一 502
        trace_id = uuid.uuid4().hex[:12]
        logger.exception("ask 失败 trace_id=%s", trace_id)  # 完整异常只留服务端日志
        raise HTTPException(
            status_code=502,
            detail={"message": "生成服务暂时不可用", "trace_id": trace_id},
        ) from e
