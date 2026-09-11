"""v0.2-hybrid:BM25(中文 bigram + ASCII 词)与向量检索的 RRF 融合。

动机(50 题冒烟发现):doc 口径 recall@5 97.5% 但 chunk 口径仅 67.5%——
向量找对文档、找不到承载答案的段落;字段值/代码细节类问题靠 BM25 精确词匹配补位。

BM25 为内置实现(rank-bm25 0.2.2 + NumPy 2.x 下 get_scores 静默全 0,见 pitfalls)。
"""

from __future__ import annotations

import math
import re

from .schemas import Hit

_CJK = r"[\u4e00-\u9fff]"
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z_][A-Za-z_0-9]*|\d+")


def tokenize_zh(text: str) -> list[str]:
    """中文按字符 bigram(单字run补unigram),ASCII 标识符/数字整词保留并小写。

    例:"allow_credentials 为空字符串时" →
    ['allow_credentials', '为空', '空字', '字符', '符串', '时']
    """
    tokens: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        seg = m.group(0)
        if re.match(_CJK, seg[0]):
            if len(seg) == 1:
                tokens.append(seg)
            else:
                tokens += [seg[i : i + 2] for i in range(len(seg) - 1)]
        else:
            tokens.append(seg.lower())
    return tokens


def rrf_fuse(*rank_lists: list[str], k: int = 60, weights: list[float] | None = None) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion:score = Σ w·1/(k+rank),支持任意路数与每路权重。

    weights 为 None 时全 1(v0.2 语义);原查询 vs 变体的加权融合见 RewriteRetriever。
    """
    ws = weights if weights else [1.0] * len(rank_lists)
    scores: dict[str, float] = {}
    for w, ranks in zip(ws, rank_lists):
        for i, cid in enumerate(ranks, 1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + i)
    return sorted(scores.items(), key=lambda x: -x[1])


class OkapiBM25:
    """Okapi BM25(Lucene 式 idf,恒正),倒排表实现。"""

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n_docs = len(corpus)
        self.doc_len = [len(d) for d in corpus]
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = {}  # term -> [(doc_i, tf)]
        for i, doc in enumerate(corpus):
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            for term, n in tf.items():
                self.postings.setdefault(term, []).append((i, n))

    def _idf(self, n_docs_with_term: int) -> float:
        return math.log(1.0 + (self.n_docs - n_docs_with_term + 0.5) / (n_docs_with_term + 0.5))

    def get_scores(self, query: list[str]) -> list[float]:
        scores = [0.0] * self.n_docs
        for term in query:
            plist = self.postings.get(term)
            if not plist:
                continue
            idf = self._idf(len(plist))
            for i, tf in plist:
                norm = 1.0 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1.0)
                scores[i] += idf * tf * (self.k1 + 1.0) / (tf + self.k1 * norm)
        return scores


class BM25Index:
    """对全部 chunk(text + section_path)建 BM25 索引,保留完整元数据供构造 Hit。"""

    def __init__(self, chunks: list[dict]):
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.ids = list(self.chunks)
        corpus = [tokenize_zh(f"{c['section_path']}\n{c['text']}") for c in chunks]
        self.bm25 = OkapiBM25(corpus)

    @classmethod
    def from_chunks_file(cls, path) -> "BM25Index":
        import json

        with open(path, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]
        return cls(chunks)

    def search(self, query: str, n: int) -> list[str]:
        scores = self.bm25.get_scores(tokenize_zh(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
        return [self.ids[i] for i in order if scores[i] > 0]

    def hit(self, chunk_id: str, index: int, score: float) -> Hit:
        c = self.chunks[chunk_id]
        return Hit(
            index=index,
            chunk_id=chunk_id,
            doc_name=c["doc_name"],
            section_path=c["section_path"],
            text=c["text"],
            score=round(score, 4),
        )


class HybridRetriever:
    """向量 + BM25 双路召回,RRF 融合。对外接口与 VectorRetriever.retrieve 一致。"""

    def __init__(self, vector, bm25: BM25Index, candidates: int = 20, rrf_k: int = 60):
        self.vector = vector
        self.bm25 = bm25
        self.candidates = candidates
        self.rrf_k = rrf_k

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        v_ids = [h.chunk_id for h in self.vector.retrieve(query, k=self.candidates)]
        b_ids = self.bm25.search(query, self.candidates)
        fused = rrf_fuse(v_ids, b_ids, k=self.rrf_k)[:k]
        return [self.bm25.hit(cid, rank, score) for rank, (cid, score) in enumerate(fused, 1)]
