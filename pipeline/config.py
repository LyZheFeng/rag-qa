"""管道配置：从仓库根 .env 读取，路径默认锚定仓库根。

非法配置在 Settings 实例化时即抛 ValidationError（启动即失败），
不留到检索阶段才暴。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
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
    # v0.7 误拒兜底:首轮 refused=true 时按 retry_k 重新检索、扩大上下文后重答一次。
    # 0=关闭。hybrid 内部本就召回 hybrid_candidates 条再融合,加深 k 不增加检索耗时。
    retry_k: int = Field(default=20, ge=0)
    # v0.9 定向改写兜底:两次都拒时让 LLM 改写问题再检索一次。
    # 200×3 实测:误拒 1.04%→0%,正确性 +0.05;代价延迟 +0.57s、正确拒答 99.2%→97.5%。
    # 默认开;想回到"无改写"行为设 RETRY_REWRITE=false。
    retry_rewrite: bool = True

    @model_validator(mode="after")
    def _check_retry_depth(self) -> "Settings":
        # 二次检索只能拿到融合候选池里的条目；比候选池还深等于静默降级
        if self.retriever != "vector" and self.retry_k > self.hybrid_candidates:
            raise ValueError(
                f"RETRY_K({self.retry_k}) 大于 HYBRID_CANDIDATES({self.hybrid_candidates})："
                "二次检索拿不到更深的命中，请调大候选深度或调小 RETRY_K"
            )
        return self
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
