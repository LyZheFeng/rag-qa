"""Phase 3 预筛:格式校验 → gold 一致性复核 → 无法回答题检索复核 → 定量选取。

原则(与红线 1/2 对应):
- 可答题不用"gold 是否检索得到"筛除——检索失败正是评估要测的(如 Depends 案例),
  只用 LLM 复核"gold chunk 是否真的支持参考答案"来剔除畸形题
- 无法回答题必须过"top-5 检索结果不含答案"复核,最终由用户在介入点 C 确认
- 复核记录全部留档(screening_report.jsonl),可追溯每题去留原因
"""

from __future__ import annotations

import sys
from collections import Counter

from .common import DATA_EVAL, REPO_ROOT, ensure_dirs, get_llm, load_jsonl, utf8_stdout, write_jsonl
from .judge import gold_supported, unanswerable_check

FINAL_TARGETS = {"fact": 100, "reasoning": 60, "unanswerable": 40}
PER_DOC_CAP = 3  # 同文档同类型最多入选数,防止单篇文档垄断


def validate_record(r: dict, chunk_ids: set[str]) -> str | None:
    """返回 None 表示通过,否则返回剔除原因。"""
    q = r.get("question", "")
    if not (8 <= len(q) <= 150):
        return f"问题长度异常({len(q)})"
    if r["type"] in ("fact", "reasoning"):
        if not r.get("answer") or len(r["answer"]) < 4:
            return "参考答案缺失"
        if r.get("gold_chunk_id") not in chunk_ids:
            return f"gold_chunk_id 不存在:{r.get('gold_chunk_id')}"
    elif r["type"] == "unanswerable":
        if not r.get("explanation"):
            return "缺覆盖不到的原因说明"
    else:
        return f"未知类型:{r['type']}"
    return None


def select_final(passed: list[dict], targets: dict[str, int] = FINAL_TARGETS) -> list[dict]:
    """按类型配额选取,同文档同类型限额,优先保留文档覆盖广的题。"""
    selected: list[dict] = []
    per_doc: Counter = Counter()
    # 两轮:第一轮尊重文档分散,第二轮放开限额补缺口
    for fill_pass in (False, True):
        for t, target in targets.items():
            have = sum(1 for r in selected if r["type"] == t)
            for r in (x for x in passed if x["type"] == t):
                if have >= target:
                    break
                key = (r["type"], r.get("gold_doc") or r["question"][:20])
                if not fill_pass and per_doc[key] >= PER_DOC_CAP:
                    continue
                if r in selected:
                    continue
                selected.append(r)
                per_doc[key] += 1
                have += 1
    return selected


def main() -> None:
    utf8_stdout()
    ensure_dirs()

    chunks = load_jsonl(REPO_ROOT / "data" / "chunks" / "chunks.jsonl")
    chunk_text = {c["chunk_id"]: c["text"] for c in chunks}
    chunk_ids = set(chunk_text)

    raw = load_jsonl(DATA_EVAL / "questions_raw.jsonl")
    print(f"原始题目 {len(raw)} 道:{Counter(r['type'] for r in raw)}")

    client, model = get_llm()
    from app.retriever import get_retriever

    retriever = get_retriever()

    report_path = DATA_EVAL / "screening_report.jsonl"
    prev_report = {}
    for x in load_jsonl(report_path):
        prev_report[x["qid"]] = x  # 同 qid 后写覆盖先写
    report_f = open(report_path, "a", encoding="utf-8")

    passed: list[dict] = []
    for i, r in enumerate(raw, 1):
        qid = r.get("qid") or f"{r['type']}-{i:03d}"
        r["qid"] = qid
        reason = validate_record(r, chunk_ids)
        if reason:
            report_f.write(_line(r, "format_reject", reason))
            continue
        if qid in prev_report:  # 断点续跑:已复核过的直接读结论
            if prev_report[qid]["decision"] == "pass":
                passed.append(r)
            continue

        if r["type"] in ("fact", "reasoning"):
            ok, why = gold_supported(client, model, r, chunk_text[r["gold_chunk_id"]])
            decision = "pass" if ok else "gold_mismatch"
        else:
            hits = retriever.retrieve(r["question"], k=5)
            answerable, why = unanswerable_check(client, model, r["question"], hits)
            ok = not answerable
            decision = "pass" if ok else "corpus_answers"
            r["top1_score"] = hits[0].score if hits else 0.0
        if ok:
            passed.append(r)
        report_f.write(_line(r, decision, why))
        print(f"[{i}/{len(raw)}] {qid} {'✓' if ok else '✗ ' + decision}: {r['question'][:36]}", flush=True)
    report_f.close()

    selected = select_final(passed)
    write_jsonl(DATA_EVAL / "questions.jsonl", selected)
    print(f"\n预筛通过 {len(passed)},定量入选 {len(selected)}:{Counter(x['type'] for x in selected)}")
    print(f"入选题覆盖文档 {len({x.get('gold_doc') for x in selected if x.get('gold_doc')})} 篇")


def _line(r: dict, decision: str, reason: str) -> str:
    import json

    return json.dumps({"qid": r["qid"], "type": r["type"], "decision": decision, "reason": reason, "question": r["question"][:60]}, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    sys.exit(main())
