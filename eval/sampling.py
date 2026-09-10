"""分层抽 chunk:按文档轮转抽样,保证文档覆盖广度、同 chunk 不重复出题。"""

from __future__ import annotations

import random


def eligible_chunks(chunks: list[dict], min_chars: int = 150) -> list[dict]:
    """出题候选:太短的 chunk 信息量不足。"""
    return [c for c in chunks if c["n_chars"] >= min_chars]


def stratified_sample(chunks: list[dict], n: int, seed: int, exclude_ids: set[str] | None = None) -> list[dict]:
    """按文档分组后轮转抽取:每轮各文档取一个未用 chunk,凑满 n 个。

    效果:覆盖尽可能多的文档;配额自动向 chunk 多的大文档倾斜(轮转后期只剩大文档)。
    """
    rng = random.Random(seed)
    exclude = set(exclude_ids or set())
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        if c["chunk_id"] in exclude:
            continue
        by_doc.setdefault(c["doc_name"], []).append(c)

    for doc in by_doc:
        rng.shuffle(by_doc[doc])
    docs = sorted(by_doc)
    rng.shuffle(docs)  # 轮转起点随机,避免每次都从 about/ 开始

    picked: list[dict] = []
    while len(picked) < n and any(by_doc.values()):
        for doc in docs:
            if len(picked) >= n:
                break
            if by_doc[doc]:
                picked.append(by_doc[doc].pop(0))
    return picked
