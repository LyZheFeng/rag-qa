"""管道配置：从仓库根 .env 读取，路径默认锚定仓库根。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

REPO_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    embed_model: str = "BAAI/bge-m3"
    hf_home: str = ""  # 为空则不覆盖环境变量
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    collection: str = "fastapi_zh_v1"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    retriever: str = "hybrid"  # "vector"(v0.1) | "hybrid"(v0.2 定版默认, BM25+RRF) | "rerank"(v0.3) 等
    hybrid_candidates: int = 20  # hybrid 每路召回深度
    rrf_k: int = 60  # RRF 融合常数

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
