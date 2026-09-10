"""Phase 3 评估跑批:RAG 全链路 + 无检索对照 + judge 三件套,记录留档 eval/runs/。

用法:
    python -m eval.run_eval --version v0.1-baseline            # 全量 200 题
    python -m eval.run_eval --version v0.2-hybrid --limit 50   # 快评子集(按类型配比抽)
    python -m eval.run_eval --version v0.2-hybrid --resume eval/runs/v0.2-hybrid_20260910_1200

纪律:temperature=0;子集数字只看趋势,进 README/results.md 的必须全量真实跑出。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from .common import DATA_EVAL, RUNS_DIR, ensure_dirs, get_llm, load_jsonl, utf8_stdout
from .judge import correctness, faithfulness_claims
from .metrics import summarize

NOCTX_PROMPT = """你是 FastAPI 技术专家,凭你已有知识直接回答用户问题。简洁作答,不要客套,不要说无法回答。

问题:{question}"""


def stratified_limit(questions: list[dict], limit: int) -> list[dict]:
    """按类型配比 5:3:2 抽前 N 题,保持与全量同分布。"""
    if limit >= len(questions):
        return questions
    per = {"fact": round(limit * 0.5), "reasoning": round(limit * 0.3), "unanswerable": limit - round(limit * 0.5) - round(limit * 0.3)}
    out = []
    for t, n in per.items():
        out += [q for q in questions if q["type"] == t][:n]
    return out


def eval_one(service, client, model: str, q: dict) -> dict:
    t0 = time.perf_counter()
    resp = service.ask(q["question"], k=5)

    rec = {
        "qid": q["qid"],
        "type": q["type"],
        "question": q["question"],
        "refused": resp.refused,
        "answer": resp.answer,
        "retrieved_ids": [h.chunk_id for h in resp.retrieved],
        "retrieved_docs": [h.doc_name for h in resp.retrieved],
        "gold_chunk_id": q.get("gold_chunk_id"),
        "gold_doc": q.get("gold_doc"),
        "retrieve_ms": resp.latency.retrieve_ms,
        "generate_ms": resp.latency.generate_ms,
        "parse_mode": resp.parse_mode,
        "cited_ids": [h.chunk_id for h in resp.cited],
    }

    if q["type"] in ("fact", "reasoning"):
        from .common import chat_text

        noctx = chat_text(client, model, NOCTX_PROMPT.format(question=q["question"]))
        rec["answer_noctx"] = noctx
        rec["correctness_noctx"] = correctness(client, model, q["question"], q["answer"], noctx)[0]
        rec["correctness"] = correctness(client, model, q["question"], q["answer"], resp.answer)[0]

    if not resp.refused:
        cited_texts = [h.text for h in resp.cited]
        rec["faithfulness"] = faithfulness_claims(client, model, resp.answer, cited_texts) if cited_texts else None
    rec["elapsed_s"] = round(time.perf_counter() - t0, 1)
    return rec


def main() -> None:
    utf8_stdout()
    ensure_dirs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="如 v0.1-baseline")
    parser.add_argument("--limit", type=int, default=0, help="子集快评题数(0=全量)")
    parser.add_argument("--resume", default="", help="断点续跑的 run 目录")
    args = parser.parse_args()

    questions = load_jsonl(DATA_EVAL / "questions.jsonl")
    if args.limit:
        questions = stratified_limit(questions, args.limit)
        print(f"快评子集 {len(questions)} 题")
    if not questions:
        print("没有可评估题目(先跑出题+预筛)")
        return 1

    if args.resume:
        run_dir = RUNS_DIR / args.resume
    else:
        run_dir = RUNS_DIR / f"{args.version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "records.jsonl"

    done = {r["qid"] for r in load_jsonl(records_path)}
    todo = [q for q in questions if q["qid"] not in done]
    print(f"run 目录 {run_dir} | 已完成 {len(done)} | 待跑 {len(todo)}")

    from app.service import get_service

    service = get_service()
    client, model = get_llm()

    f = open(records_path, "a", encoding="utf-8")
    t0 = time.time()
    for i, q in enumerate(todo, 1):
        rec = eval_one(service, client, model, q)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        speed = (time.time() - t0) / i
        eta = speed * (len(todo) - i) / 60
        mark = "拒答" if rec["refused"] else f"正确性{rec.get('correctness', '-')}"
        print(f"[{i}/{len(todo)}] {q['qid']} {mark} ({rec['elapsed_s']}s, ETA {eta:.0f}min)", flush=True)
    f.close()

    records = load_jsonl(records_path)
    records = [r for r in records if r["qid"] in {q["qid"] for q in questions}]
    summary = {"version": args.version, "limit": args.limit or "full", **summarize(records)}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
