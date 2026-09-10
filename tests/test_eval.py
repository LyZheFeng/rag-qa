"""Phase 3 评估模块单测(纯函数,无网络)。"""

from eval.metrics import faithfulness_score, mean, recall_chunk, recall_doc, reciprocal_rank, summarize
from eval.sampling import eligible_chunks, stratified_sample
from eval.screen import select_final, validate_record


def _chunk(cid, doc, n=200):
    return {"chunk_id": cid, "doc_name": doc, "n_chars": n, "section_path": "s", "text": "t"}


# ---------- sampling ----------

def test_eligible_filters_short():
    chunks = [_chunk("a#0", "a.md", 100), _chunk("b#0", "b.md", 150)]
    assert [c["chunk_id"] for c in eligible_chunks(chunks)] == ["b#0"]


def test_stratified_covers_docs_and_no_repeat():
    chunks = [_chunk(f"d{i}#{j}", f"d{i}.md") for i in range(5) for j in range(4)]
    picked = stratified_sample(chunks, 10, seed=42)
    assert len(picked) == 10
    assert len({c["chunk_id"] for c in picked}) == 10  # 不重复
    assert len({c["doc_name"] for c in picked}) == 5  # 覆盖全部文档(轮转)


def test_stratified_respects_exclude():
    chunks = [_chunk(f"d{i}#0", f"d{i}.md") for i in range(5)]
    picked = stratified_sample(chunks, 5, seed=1, exclude_ids={"d0#0", "d1#0"})
    assert {c["chunk_id"] for c in picked} == {"d2#0", "d3#0", "d4#0"}


# ---------- screen ----------

def test_validate_rejects_bad():
    assert validate_record({"type": "fact", "question": "x" * 10, "answer": "answer", "gold_chunk_id": "nope"}, {"a#0"}) == "gold_chunk_id 不存在:nope"
    assert validate_record({"type": "fact", "question": "太短", "answer": "answer", "gold_chunk_id": "a#0"}, {"a#0"}) is not None
    assert validate_record({"type": "fact", "question": "x" * 10, "answer": "ok", "gold_chunk_id": "a#0"}, {"a#0"}) is not None  # 答案太短
    assert validate_record({"type": "unanswerable", "question": "x" * 10, "explanation": "e"}, set()) is None


def test_select_final_quota_and_doc_cap():
    fact = [{"type": "fact", "qid": f"f{i}", "gold_doc": "docA.md", "question": f"q{i}"} for i in range(10)]
    out = select_final(fact, targets={"fact": 4})
    assert len(out) == 4
    out = select_final(fact, targets={"fact": 10})  # 超出单文档限额也能补满
    assert len(out) == 10


# ---------- metrics ----------

def test_recall_and_mrr():
    ids = ["a", "b", "c", "d", "e"]
    assert recall_chunk(ids, "b", 5) == 1
    assert recall_chunk(ids, "b", 1) == 0
    assert recall_doc(["d1", "d2"], "d2", 2) == 1
    assert reciprocal_rank(ids, "c") == 1 / 3
    assert reciprocal_rank(ids, "z") == 0.0
    assert reciprocal_rank(ids, None) == 0.0


def test_faithfulness():
    claims = [{"claim": "a", "supported": True}, {"claim": "b", "supported": False}]
    assert faithfulness_score(claims) == 0.5
    assert faithfulness_score([]) is None
    assert faithfulness_score(None) is None


def _rec(**kw):
    base = {
        "qid": "x", "type": "fact", "refused": False, "retrieved_ids": ["a", "b"],
        "retrieved_docs": ["d.md", "e.md"], "gold_chunk_id": "a", "gold_doc": "d.md",
        "correctness": 5, "correctness_noctx": 3,
        "faithfulness": [{"claim": "c", "supported": True}],
    }
    base.update(kw)
    return base


def test_summarize_full_picture():
    s = summarize([_rec(), _rec(type="unanswerable", gold_chunk_id=None, gold_doc=None, refused=True, correctness=None, correctness_noctx=None)])
    assert s["recall@5_chunk"] == 1.0  # 唯一可答题 gold 命中 top-1
    assert s["recall@5_doc"] == 1.0
    assert s["正确拒答率(无法答题)"] == 1.0
    assert s["误拒率(可答题拒答)"] == 0.0
    assert s["正确性_无检索对照"] == 3.0
    assert s["faithfulness"] == 1.0
    assert s["faithfulness_n"] == 1


def test_summarize_refused_excluded_from_faithfulness():
    s = summarize([_rec(refused=True, faithfulness=None)])
    assert s["faithfulness_n"] == 0
    assert s["误拒率(可答题拒答)"] == 1.0
