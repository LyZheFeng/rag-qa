"""Phase 2 数据契约：LLM 输出、检索命中、API 请求/响应。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnswerSpec(BaseModel):
    """LLM 输出契约（严格 JSON）。"""

    answer: str
    citations: list[int] = Field(default_factory=list)
    refused: bool = False


class Hit(BaseModel):
    """一条检索命中，index 为喂给 LLM 的编号（1 起）。"""

    index: int
    chunk_id: str
    doc_name: str
    section_path: str
    text: str
    score: float  # 相似度 = 1 - cos 距离


class Latency(BaseModel):
    retrieve_ms: int
    generate_ms: int
    total_ms: int


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=5, ge=1, le=10)


class AskResponse(BaseModel):
    question: str
    answer: str
    refused: bool
    parse_mode: Literal["json", "retry", "fallback"]
    cited: list[Hit]
    retrieved: list[Hit]
    latency: Latency
