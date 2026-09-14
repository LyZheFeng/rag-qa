"""bge-m3 嵌入（本地 sentence-transformers，CPU）。"""

from __future__ import annotations

import os
from pathlib import Path


class BgeM3Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        # 仅当模型已在 HF 缓存时才禁网(防偶发重连);全新环境(如容器首启)必须放行下载
        cache_marker = Path(os.environ.get("HF_HOME", "")) / "hub" / ("models--" + model_name.replace("/", "--"))
        if cache_marker.exists():
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
        # 5.0 起改名 get_embedding_dimension;hasattr 兼容 <5 的旧名
        if hasattr(self.model, "get_embedding_dimension"):
            self.dim = self.model.get_embedding_dimension()
        else:
            self.dim = self.model.get_sentence_embedding_dimension()

    def encode_corpus(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        vecs = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vecs]

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return self.encode_corpus(texts, batch_size=16)
