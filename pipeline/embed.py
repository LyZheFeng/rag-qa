"""bge-m3 嵌入（本地 sentence-transformers，CPU）。"""

from __future__ import annotations

import os


class BgeM3Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 模型已缓存，禁网避免偶发重连
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
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
