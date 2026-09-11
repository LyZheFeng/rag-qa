"""FastAPI 服务：POST /ask 问答 + GET /health。

启动（仓库根）：uvicorn app.api:app --port 8000
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # streamlit/uvicorn 任意 cwd 下可 import

from fastapi import FastAPI, HTTPException, Request

from .schemas import AskRequest, AskResponse
from .service import RagService, get_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = get_service()  # 启动即预热嵌入模型，首问不付 2.4s
    yield


app = FastAPI(title="rag-qa", version="0.1.0", lifespan=lifespan)


def _svc(request: Request) -> RagService:
    return getattr(request.app.state, "service", None) or get_service()


@app.get("/health")
def health(request: Request) -> dict:
    svc = _svc(request)
    r = svc.retriever  # 沿包装链下钻到 VectorRetriever(vector/base/child 三种包装名)
    while not hasattr(r, "collection"):
        r = getattr(r, "vector", None) or getattr(r, "base", None) or getattr(r, "child", None)
        if r is None:
            raise HTTPException(status_code=500, detail="无法定位底层向量检索器")
    return {
        "status": "ok",
        "retriever": type(svc.retriever).__name__,
        "chunks": r.collection.count(),
        "embed_dim": r.embedder.dim,
        "llm_model": svc.generator.model,
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    try:
        return _svc(request).ask(req.question, k=req.k)
    except Exception as e:  # vLLM 断连/超时等，统一 502
        raise HTTPException(status_code=502, detail=f"生成失败：{type(e).__name__}: {e}") from e
