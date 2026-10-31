"""Phase 3 评估跑批:RAG 全链路 + 无检索对照 + judge 三件套,记录留档 eval/runs/。

用法:
    python -m eval.run_eval --version v0.1-baseline            # 全量 200 题
    python -m eval.run_eval --version v0.2-hybrid --limit 50   # 快评子集(按类型配比抽)
    python -m eval.run_eval --version v0.2-hybrid --resume eval/runs/v0.2-hybrid_20260910_1200

纪律:temperature=0;子集数字只看趋势,进 README/results.md 的必须全量真实跑出。
判分模型由 .env 的 JUDGE_MODEL 决定(留空则与生成模型相同);换生成模型时固定 judge,
正确性/faithfulness 才与历史行可比。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .common import (
    DATA_EVAL,
    REPO_ROOT,
    RUNS_DIR,
    ensure_dirs,
    get_judge,
    get_llm,
    judge_unanswerable,
    load_jsonl,
    utf8_stdout,
)
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


def eval_one(service, gen, judge, q: dict) -> dict:
    """gen 用于作答与无检索对照，judge 只用于打分（两者可以是不同模型）。"""
    gen_client, gen_model = gen
    judge_client, judge_model = judge
    t0 = time.perf_counter()
    resp = service.ask(q["question"])

    rec = {
        "qid": q["qid"],
        "type": q["type"],
        "question": q["question"],
        "refused": resp.refused,
        "retried": resp.retried,
        "rewritten": resp.rewritten,
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

        noctx = chat_text(gen_client, gen_model, NOCTX_PROMPT.format(question=q["question"]))
        rec["answer_noctx"] = noctx
        rec["correctness_noctx"] = correctness(judge_client, judge_model, q["question"], q["answer"], noctx)[0]
        rec["correctness"] = correctness(judge_client, judge_model, q["question"], q["answer"], resp.answer)[0]

    if q["type"] == "unanswerable":
        # 安全口径：拒答天然安全；没拒的交给 judge 判「明确声明缺失且未编造」
        if resp.refused:
            rec["unanswerable_safe"] = True
        else:
            rec["unanswerable_safe"], rec["unanswerable_safe_reason"] = judge_unanswerable(
                judge_client, judge_model, q["question"], resp.answer, [h.text for h in resp.cited]
            )

    if not resp.refused:
        cited_texts = [h.text for h in resp.cited]
        rec["faithfulness"] = faithfulness_claims(judge_client, judge_model, resp.answer, cited_texts) if cited_texts else None
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
        cand = Path(args.resume)
        if not cand.is_absolute():
            cand = REPO_ROOT / cand
        run_dir = cand if cand.exists() else RUNS_DIR / args.resume
    else:
        run_dir = RUNS_DIR / f"{args.version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "records.jsonl"

    done = {r["qid"] for r in load_jsonl(records_path)}
    todo = [q for q in questions if q["qid"] not in done]
    print(f"run 目录 {run_dir} | 已完成 {len(done)} | 待跑 {len(todo)}")

    from app.service import get_service

    service = get_service()
    gen = get_llm()
    judge = get_judge()
    print(f"生成模型 {gen[1]} | judge {judge[1]}", flush=True)

    f = open(records_path, "a", encoding="utf-8")
    t0 = time.time()
    for i, q in enumerate(todo, 1):
        rec = None
        for attempt in (1, 2, 3):  # 单题失败不拖垮整轮:退避重试
            try:
                rec = eval_one(service, gen, judge, q)
                break
            except Exception as e:  # noqa: BLE001 —— 网络/限流/单题异常
                print(f"[{i}/{len(todo)}] {q['qid']} 第 {attempt} 次失败:{type(e).__name__}: {e}", flush=True)
                time.sleep(5 * attempt)
        if rec is None:  # 三次仍失败:记错误继续跑,汇总里看得到
            rec = {
                "qid": q["qid"], "type": q["type"], "question": q["question"],
                "refused": False, "answer": "", "retrieved_ids": [], "retrieved_docs": [],
                "gold_chunk_id": q.get("gold_chunk_id"), "gold_doc": q.get("gold_doc"),
                "retrieve_ms": 0, "generate_ms": 0, "parse_mode": "error", "cited_ids": [],
                "error": "eval_failed_after_retries",
            }
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        speed = (time.time() - t0) / i
        eta = speed * (len(todo) - i) / 60
        mark = "拒答" if rec["refused"] else f"正确性{rec.get('correctness', '-')}"
        print(f"[{i}/{len(todo)}] {q['qid']} {mark} ({rec['elapsed_s']}s, ETA {eta:.0f}min)", flush=True)
    f.close()

    records = load_jsonl(records_path)
    records = [r for r in records if r["qid"] in {q["qid"] for q in questions}]
    summary = {
        "version": args.version,
        "limit": args.limit or "full",
        "llm_model": gen[1],
        "judge_model": judge[1],
        "errors": sum(1 for r in records if r.get("error")),
        **summarize(records),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
