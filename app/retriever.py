"""向量检索：bge-m3 编码查询 → Chroma top-k。"""

from __future__ import annotations

from functools import lru_cache

from pipeline.config import get_settings
from pipeline.store import get_collection

from .schemas import Hit


class VectorRetriever:
    def __init__(self, collection, embedder):
        self.collection = collection
        self.embedder = embedder

    @classmethod
    def from_settings(cls, collection_name: str | None = None) -> "VectorRetriever":
        s = get_settings()
        from pipeline.embed import BgeM3Embedder

        return cls(
            get_collection(s.chroma_dir, collection_name or s.collection),
            BgeM3Embedder(s.embed_model),
        )

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        vec = self.embedder.encode_queries([query])[0]
        res = self.collection.query(
            query_embeddings=[vec],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[Hit] = []
        for i, (doc, meta, dist) in enumerate(
            zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ):
            if "chunk_id" not in meta:
                # 旧库未存 chunk_id，按 models.Doc.stem 约定重构 "{stem}#{seq:04d}"
                meta["chunk_id"] = meta["doc_name"][: -len(".md")].replace("/", ".") + f"#{meta['seq']:04d}"
            hits.append(
                Hit(
                    index=i + 1,
                    chunk_id=meta["chunk_id"],
                    doc_name=meta["doc_name"],
                    section_path=meta["section_path"],
                    text=doc,
                    score=round(1 - dist, 4),
                )
            )
        return hits


@lru_cache(maxsize=1)
def get_retriever() -> VectorRetriever:
    """进程内单例:嵌入模型加载 ~2.4s,只付一次。RETRIEVER=hybrid 时返回融合检索。"""
    from pipeline.config import get_settings

    s = get_settings()
    base = VectorRetriever.from_settings()
    if s.retriever != "hybrid":
        return base
    from .hybrid import BM25Index, HybridRetriever

    return HybridRetriever(base, BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k)
