"""v0.2-hybrid 单测:分词、RRF 融合、BM25 索引与 HybridRetriever(无网络)。"""

from app.hybrid import BM25Index, HybridRetriever, rrf_fuse, tokenize_zh


def test_tokenize_mixed():
    toks = tokenize_zh("allow_credentials 为空字符串时返回 422")
    assert toks[:1] == ["allow_credentials"]
    assert "为空" in toks and "空字" in toks and "422" in toks
    assert all(t == t.lower() for t in toks if t.isascii())


def test_tokenize_single_cjk_char():
    assert tokenize_zh("值") == ["值"]
    assert tokenize_zh("类型") == ["类型"]


def test_rrf_fuse_prefers_dual_agreement():
    # id "b" 两路都靠前,应排第一
    fused = rrf_fuse(["a", "b", "c"], ["d", "b", "e"])
    assert fused[0][0] == "b"
    ids = [x for x, _ in fused]
    assert set(ids) == {"a", "b", "c", "d", "e"}
    # 分数单调不增
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_k_scales():
    a = rrf_fuse(["x"], [], k=60)
    assert a[0][1] == 1 / 61


def _chunks():
    return [
        {"chunk_id": "doc.a#0000", "doc_name": "doc/a.md", "seq": 0,
         "section_path": "查询参数校验", "text": "缺少必选查询参数 needy 时,错误响应 detail 里 type 为 missing,msg 为 Field required",
         "n_chars": 50, "char_span": [0, 50], "hash": "h1"},
        {"chunk_id": "doc.b#0000", "doc_name": "doc/b.md", "seq": 0,
         "section_path": "背景", "text": "FastAPI 是一个高性能 Web 框架,基于标准 Python 类型提示",
         "n_chars": 30, "char_span": [0, 30], "hash": "h2"},
    ]


def test_bm25_exact_terms_beat_semantic_noise():
    idx = BM25Index(_chunks())
    top = idx.search("查询参数缺少时 detail 的 type 和 msg 是什么", n=2)
    assert top[0] == "doc.a#0000"


def test_hybrid_retriever_full_hits():
    class FakeVector:
        def retrieve(self, query, k=5):
            from app.schemas import Hit

            return [Hit(index=1, chunk_id="doc.b#0000", doc_name="doc/b.md",
                        section_path="背景", text="FastAPI 框架", score=0.9),
                    Hit(index=2, chunk_id="doc.a#0000", doc_name="doc/a.md",
                        section_path="查询参数校验", text="参数校验", score=0.8)]

    idx = BM25Index(_chunks())
    hy = HybridRetriever(FakeVector(), idx, candidates=2)
    hits = hy.retrieve("查询参数缺少时 type msg", k=2)
    assert len(hits) == 2
    assert [h.index for h in hits] == [1, 2]
    # A:向量 rank2(1/62) + BM25 rank1(1/61) > B:仅向量 rank1(1/61)
    assert hits[0].chunk_id == "doc.a#0000"
    assert hits[0].text  # 融合命中都有完整正文


def test_rerank_reorders_and_truncates():
    from app.rerank import RerankRetriever
    from app.schemas import Hit

    def mk(i, text):
        return Hit(index=i, chunk_id=f"c{i}", doc_name="d.md", section_path="s", text=text, score=0.5)

    class FakeBase:
        def retrieve(self, query, k=5):
            return [mk(1, "甲"), mk(2, "乙"), mk(3, "丙")]

    class FakeReranker:  # 丙 > 甲 > 乙
        def predict(self, pairs):
            order = {"丙": 0.9, "甲": 0.8, "乙": 0.1}
            return [order[p[1]] for p in pairs]

    rr = RerankRetriever(FakeBase(), reranker=FakeReranker(), candidates=3)
    hits = rr.retrieve("q", k=2)
    assert [h.chunk_id for h in hits] == ["c3", "c1"]  # 按精排分重排并截断
    assert [h.index for h in hits] == [1, 2]
    assert hits[0].score == 0.9


def test_rerank_pool_le_k_passthrough():
    from app.rerank import RerankRetriever

    class FakeBase:
        def retrieve(self, query, k=5):
            return ["x"] * (k - 1)  # 少于 k,直接返回不精排

    class Boom:
        def predict(self, pairs):
            raise AssertionError("不应调用精排")

    rr = RerankRetriever(FakeBase(), reranker=Boom(), candidates=3)
    assert rr.retrieve("q", k=3) == ["x", "x"]
