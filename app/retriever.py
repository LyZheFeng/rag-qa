"""向量检索：bge-m3 编码查询 → Chroma top-k。"""

from __future__ import annotations

import logging
from functools import lru_cache

from pipeline.config import get_settings
from pipeline.store import get_collection

from .schemas import Hit

# 沿用 uvicorn 的错误日志通道（服务端免配置可见）；其他宿主落到 root 兜底输出
logger = logging.getLogger("uvicorn.error")


def _validate_index(
    chroma_dir,
    chunks_path,
    *,
    collection: str,
    embed_model: str,
    check_count: bool = True,
    label: str = "",
):
    """manifest 绑定校验：chunks 哈希 / collection / 嵌入模型（可选条数）。

    mismatch → IndexValidationError（RuntimeError 子类）拒绝启动（在加载嵌入
    模型之前，秒级失败）；missing（旧索引无 manifest）→ 警告放行。
    """
    from pipeline.manifest import IndexValidationError, check_manifest

    tag = label or collection
    state, msg, m = check_manifest(chroma_dir, chunks_path, collection=collection, embed_model=embed_model)
    if state == "mismatch":
        raise IndexValidationError(f"索引版本校验失败[{tag}]：{msg}")
    if state == "missing":
        logger.warning("索引校验跳过[%s]：%s", tag, msg)
        return
    if check_count:
        actual = get_collection(chroma_dir, collection).count()
        if actual != m.get("chunk_count"):
            raise IndexValidationError(
                f"索引版本校验失败[{tag}]：Chroma 条数 {actual} 与 manifest {m.get('chunk_count')} 不一致"
            )
    logger.info("索引校验通过[%s]：%s（embed=%s）", tag, msg, embed_model)


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
    """进程内单例:嵌入模型加载 ~2.4s,只付一次。
    RETRIEVER: vector(v0.1) | hybrid(v0.2) | rerank(v0.3, hybrid 粗排+精排)。"""
    from pipeline.config import get_settings

    s = get_settings()
    if s.retriever == "parentchild":
        # 按实际使用的索引校验：子块向量库严格校验（真正被查询的 collection）；
        # 父块只读 jsonl，主 collection 此模式不查询，免条数比对
        _validate_index(
            s.chroma_dir, s.chunks_dir / "chunks_pc.jsonl",
            collection="fastapi_zh_pc", embed_model=s.embed_model, label="parentchild/child",
        )
        _validate_index(
            s.chroma_dir, s.chunks_path, collection=s.collection,
            embed_model=s.embed_model, check_count=False, label="parentchild/parent",
        )
    else:
        _validate_index(s.chroma_dir, s.chunks_path, collection=s.collection, embed_model=s.embed_model)

    base = VectorRetriever.from_settings()
    if s.retriever == "vector":
        return base

    from .hybrid import BM25Index, HybridRetriever

    hybrid = HybridRetriever(base, BM25Index.from_chunks_file(s.chunks_path), s.hybrid_candidates, s.rrf_k)
    if s.retriever == "hybrid":
        return hybrid
    if s.retriever == "rerank":
        from .rerank import RerankRetriever

        return RerankRetriever(hybrid, candidates=s.hybrid_candidates)
    if s.retriever == "rewrite":
        from openai import OpenAI

        from .rewrite import QueryRewriter, RewriteRetriever

        client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=30)
        rewriter = QueryRewriter(client, s.llm_model)
        return RewriteRetriever(hybrid, rewriter.rewrite, s.hybrid_candidates, s.rrf_k)
    if s.retriever == "parentchild":  # v0.5:子块检索 → 父块(整节)喂生成
        from .hybrid import BM25Index as _BMI
        from .parentchild import ParentChildRetriever, build_pc_maps

        child_vec = VectorRetriever.from_settings("fastapi_zh_pc")
        child_hybrid = HybridRetriever(child_vec, _BMI.from_chunks_file(s.chunks_dir / "chunks_pc.jsonl"), s.hybrid_candidates, s.rrf_k)
        c2p, parents = build_pc_maps(s.chunks_dir)
        return ParentChildRetriever(child_hybrid, c2p, parents, candidates=s.hybrid_candidates)
    raise ValueError(f"未知 RETRIEVER 配置:{s.retriever}")
