"""Chroma 持久化：确定性 chunk_id + 按文档先删后加，重跑幂等。"""

from __future__ import annotations

from pathlib import Path

import chromadb

from .models import Chunk


def get_collection(path: Path, name: str):
    client = chromadb.PersistentClient(path=str(path))
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "chunker": "heading-512-50"},
    )


def upsert_chunks(collection, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
    if not chunks:
        return 0
    doc_names = sorted({c.doc_name for c in chunks})
    for dn in doc_names:
        try:
            collection.delete(where={"doc_name": dn})
        except Exception:
            pass  # 文档首次入库时无旧数据
    collection.upsert(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "doc_name": c.doc_name,
                "seq": c.seq,
                "section_path": c.section_path,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "n_chars": c.n_chars,
                "hash": c.hash,
            }
            for c in chunks
        ],
    )
    return len(chunks)
