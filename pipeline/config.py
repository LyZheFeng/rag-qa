"""管道配置：从仓库根 .env 读取，路径默认锚定仓库根。

非法配置在 Settings 实例化时即抛 ValidationError（启动即失败），
不留到检索阶段才暴。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[1]

# app/api.py 的 k 参数上限；hybrid/rerank 的候选深度不小于它，否则融合后不足 k 条
API_MAX_K = 10


class Settings(BaseSettings):
    embed_model: str = "BAAI/bge-m3"
    hf_home: str = ""  # 为空则不覆盖环境变量
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # 平台专属请求字段(JSON),默认不发送。
    # DeepSeek: {"thinking": {"type": "disabled"}}
    # vLLM/Qwen: {"chat_template_kwargs": {"enable_thinking": false}}
    llm_extra_body: dict = Field(default_factory=dict)
    # judge(判分)独立配置:留空则回落到上面的生成模型(旧行为)。
    # 换生成模型时把 judge 固定为历史同一模型,数字才可比。
    judge_base_url: str = ""
    judge_api_key: str = ""
    judge_model: str = ""
    # judge 专属请求字段:不同模型关思考的参数不一样(DeepSeek 认 thinking,
    # Qwen/vLLM 认 chat_template_kwargs),留空回落到 llm_extra_body。
    judge_extra_body: dict = Field(default_factory=dict)
    collection: str = "fastapi_zh_v1"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    retriever: Literal["vector", "hybrid", "rerank", "rewrite", "parentchild"] = "hybrid"  # v0.2 定版默认
    hybrid_candidates: int = Field(default=20, ge=API_MAX_K)  # hybrid 每路召回深度
    rrf_k: int = Field(default=60, ge=1)  # RRF 融合常数
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"  # 逗号分隔，本地前端开发端口

    model_config = {"env_file": REPO_ROOT / ".env", "extra": "ignore"}

    @property
    def corpus_root(self) -> Path:
        return REPO_ROOT / "data" / "raw" / "fastapi-zh"

    @property
    def docs_src_root(self) -> Path:
        return REPO_ROOT / "data" / "raw" / "fastapi-docs-src"

    @property
    def chunks_dir(self) -> Path:
        return REPO_ROOT / "data" / "chunks"

    @property
    def chunks_path(self) -> Path:
        return self.chunks_dir / "chunks.jsonl"

    @property
    def chroma_dir(self) -> Path:
        return REPO_ROOT / "data" / "chroma"


def get_settings() -> Settings:
    s = Settings()
    if s.hf_home:
        import os

        os.environ.setdefault("HF_HOME", s.hf_home)
    return s
