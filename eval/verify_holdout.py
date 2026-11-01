"""用独立模型审核留出集：gold 段落是否支持参考答案；无法回答题是否真的无法回答。

用法:
    python -m eval.verify_holdout --model deepseek-v4-pro
    python -m eval.verify_holdout --model deepseek-v4-pro --file holdout.jsonl

answerable 题：把问题、gold 段落原文、参考答案给审核模型，判 supported/clear/correct；
unanswerable 题：对问题做 k=20 检索，把命中段落给审核模型，判语料里是否真的能回答。

只读，不改题库；审核不通过的题会列出，由人工修正后重跑。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import REPO_ROOT, chat_json, get_llm, load_jsonl, utf8_stdout

ANSWERABLE_REVIEW = """你在审核一个 RAG 评测集的题目。下面给出问题、gold 段落原文、参考答案。

问题:{question}

gold 段落原文:
{chunk}

参考答案:{answer}

请判断：
1. supported：参考答案是否完全由上述段落支持（允许措辞不同，但不能依赖段落之外的知识）；
2. clear：问题是否清晰、能被该段落明确回答（不能有歧义或需要额外上下文）；
3. correct：参考答案是否正确、完整、没有编造。

只输出 JSON：{{"supported": true/false, "clear": true/false, "correct": true/false, "issues": ["..."], "suggested_answer": "若参考答案有问题，给出一句修正版；否则留空"}}"""

UNANSWERABLE_REVIEW = """你在审核一个 RAG 评测集中的「无法回答」题。语料是 FastAPI 官方中文文档。
下面给出问题，以及检索到的 top 段落。请判断：这些段落里是否有任何一段**实际包含**该问题的答案。

问题:{question}

检索段落:
{chunks}

注意：只有相关术语、相关主题但缺少答案，判 answerable=false；任何一段真正回答了问题，判 true。
只输出 JSON：{{"answerable": true/false, "evidence_index": 段落编号或 null, "reason": "一句话"}}"""


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="holdout.jsonl")
    ap.add_argument("--model", default="deepseek-v4-pro")
    ap.add_argument("--k", type=int, default=20)
    args = ap.parse_args()

    qs = load_jsonl(REPO_ROOT / "data" / "eval" / args.file)
    chunks = {c["chunk_id"]: c for c in load_jsonl(REPO_ROOT / "data" / "chunks" / "chunks.jsonl")}
    client, _ = get_llm()

    retriever = None
    bad = 0
    for q in qs:
        if q["type"] == "unanswerable":
            if retriever is None:
                from app.retriever import get_retriever

                retriever = get_retriever()
            hits = retriever.retrieve(q["question"], k=args.k)
            text = "\n\n".join(
                f"[{i}] {h.doc_name} > {h.section_path}\n{h.text[:350]}" for i, h in enumerate(hits, 1)
            )
            obj = chat_json(client, args.model, UNANSWERABLE_REVIEW.format(question=q["question"], chunks=text),
                            max_tokens=800) or {}
            ok = obj.get("answerable") is False
            print(f"{q['qid']} unans {'OK' if ok else 'BAD'} answerable={obj.get('answerable')}"
                  f" evidence={obj.get('evidence_index')} {str(obj.get('reason', ''))[:80]}", flush=True)
        else:
            chunk = chunks.get(q["gold_chunk_id"])
            if not chunk:
                print(f"{q['qid']} BAD gold chunk missing: {q['gold_chunk_id']}", flush=True)
                bad += 1
                continue
            obj = chat_json(
                client, args.model,
                ANSWERABLE_REVIEW.format(question=q["question"], chunk=chunk["text"][:1600], answer=q["answer"]),
                max_tokens=900,
            ) or {}
            ok = all(obj.get(k) is True for k in ("supported", "clear", "correct"))
            print(f"{q['qid']} {q['type']} {'OK' if ok else 'BAD'}"
                  f" supported={obj.get('supported')} clear={obj.get('clear')} correct={obj.get('correct')}"
                  f" issues={obj.get('issues')}", flush=True)
            if not ok and obj.get("suggested_answer"):
                print(f"      suggested: {obj['suggested_answer'][:200]}", flush=True)
        if not ok:
            bad += 1

    print(f"\n审核完成：{len(qs)} 题，不通过 {bad} 题")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())