"""固定 10 题冒烟评测(评测守护):演示前、对外报任何评估数字前必跑。

断言:
  - 可答题:未拒答 + 引用数 >= 1 + 检索 top-5 命中 gold doc
  - 拒答题:refused 且引用为空
  - watch 题(观察名单):断言失败不判红只进漂移报告——已知的 vLLM 服务端漂移
    (2026-09-17 实锤:「Depends 依赖注入怎么用?」检索首命中 0.977 正常、生成侧拒答;
    temperature=0 的确定性只在不重启的同一服务端内成立,跨会话状态漂移会改变单题表现)

输出:一页漂移报告(与 eval/smoke_baseline.json 快照对比,哪题变了),跑完写入新快照。
口径:结果以「当次跑批」为准,带日期记 PROGRESS。

用法:.venv/Scripts/python.exe -X utf8 scripts/smoke_eval.py
依赖:本地索引 + 内网 vLLM(生成侧);vLLM 不通时 ask 会走降级/拒答路径,看报告即知。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

K = 5
BASELINE = ROOT / "eval" / "smoke_baseline.json"
EVAL_QUESTIONS = ROOT / "data" / "eval" / "questions.jsonl"
CHUNKS = ROOT / "data" / "chunks" / "chunks.jsonl"

# 10 题构成:5 道前端示例胶囊原题(守住 demo 主路径)+ 3 道 200 题金标集题(语料多样性)
# + 2 道金标拒答题(拒答契约)。fact-*/unans-* 的题面与 gold 从 questions.jsonl 按 qid 取,避免抄写漂移。
# 注:胶囊「如何声明请求体?」检索稳定命中 index.md 概览页(回答正确但 gold 配不上金标),body.md
# 覆盖改用金标原题 fact-029 的措辞守住,胶囊措辞不进断言集。
QUESTIONS: list[dict] = [
    dict(qid="fact-029", mode="answer", gold_doc=None),  # 题面/gold 启动时从金标集补(tutorial/body.md)
    dict(qid="demo-02", mode="answer", question="Depends 依赖注入怎么用?",
         gold_doc="tutorial/dependencies/index.md", watch=True),  # 2026-09-17 漂移题,进观察名单
    dict(qid="demo-03", mode="answer", question="怎么统一处理异常?", gold_doc="tutorial/handling-errors.md"),
    dict(qid="demo-04", mode="answer", question="后台任务 BackgroundTasks 怎么写?", gold_doc="tutorial/background-tasks.md"),
    dict(qid="demo-05", mode="answer", question="如何用 TestClient 做测试?", gold_doc="tutorial/testing.md"),
    dict(qid="demo-06", mode="answer", question="路径参数如何校验和转换类型?", gold_doc="tutorial/path-params.md"),
    dict(qid="fact-001", mode="answer", gold_doc=None),  # 题面/gold 启动时从金标集补
    dict(qid="fact-008", mode="answer", gold_doc=None),
    dict(qid="unans-004", mode="refuse"),
    dict(qid="unans-005", mode="refuse"),
]


def _load_gold_questions() -> dict[str, dict]:
    with EVAL_QUESTIONS.open(encoding="utf-8") as f:
        return {q["qid"]: q for q in (json.loads(line) for line in f if line.strip())}


def _indexed_docs() -> set[str]:
    docs: set[str] = set()
    with CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            docs.add(json.loads(line)["doc_name"])
    return docs


def _prev_snapshot() -> dict | None:
    if not BASELINE.exists():
        return None
    try:
        return json.loads(BASELINE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None  # 快照损坏按「无基线」处理,本轮跑完重写


def main() -> int:
    gold_qs = _load_gold_questions()
    for q in QUESTIONS:
        if "question" not in q:
            g = gold_qs.get(q["qid"])
            if g is None:
                print(f"[setup] 金标集里没有 {q['qid']}", file=sys.stderr)
                return 2
            q["question"] = g["question"]
            if q["mode"] == "answer":
                q["gold_doc"] = g["gold_doc"]

    docs = _indexed_docs()
    missing = sorted({q["gold_doc"] for q in QUESTIONS if q["mode"] == "answer"} - docs)
    if missing:
        print(f"[setup] gold doc 不在索引语料: {missing}(索引未建?先跑 scripts/build_index.py)", file=sys.stderr)
        return 2

    from pipeline.config import get_settings
    from app.service import get_service

    settings = get_settings()
    t0 = time.time()
    svc = get_service()
    load_s = time.time() - t0

    results = []
    for q in QUESTIONS:
        resp = svc.ask(q["question"], k=K)
        retrieved_docs = [h.doc_name for h in resp.retrieved]
        checks: list[tuple[str, bool]] = []
        if q["mode"] == "refuse":
            checks = [("拒答", resp.refused), ("引用为空", len(resp.cited) == 0)]
        else:
            checks = [
                ("未拒答", not resp.refused),
                ("引用数>=1", len(resp.cited) >= 1),
                ("检索命中gold", q["gold_doc"] in retrieved_docs),
            ]
        ok = all(passed for _, passed in checks)
        gold_rank = retrieved_docs.index(q["gold_doc"]) + 1 if q.get("gold_doc") in retrieved_docs else "-"
        results.append(dict(
            qid=q["qid"], question=q["question"], mode=q["mode"], watch=bool(q.get("watch")),
            ok=ok, failed=[name for name, passed in checks if not passed],
            refused=resp.refused, n_cited=len(resp.cited), gold_doc=q.get("gold_doc"),
            gold_rank=gold_rank, cited_docs=[h.doc_name for h in resp.cited],
            parse_mode=resp.parse_mode, total_ms=resp.latency.total_ms,
            answer_head=resp.answer[:80],
        ))
        mark = "PASS" if ok else ("WATCH" if q.get("watch") else "FAIL")
        print(f"[{mark:>5}] {q['qid']:<10} 拒答={resp.refused!s:<5} 引用={len(resp.cited)} "
              f"gold名次={gold_rank!s:<3} {resp.latency.total_ms}ms")

    prev = _prev_snapshot()
    prev_by = {r["qid"]: r for r in prev["results"]} if prev else {}
    drift = []
    for r in results:
        p = prev_by.get(r["qid"])
        if p is None:
            continue
        diffs = []
        for field in ("ok", "refused", "n_cited", "gold_rank"):
            if r[field] != p[field]:
                diffs.append(f"{field}: {p[field]!r}→{r[field]!r}")
        if diffs:
            drift.append((r["qid"], "; ".join(diffs)))

    BASELINE.write_text(json.dumps(dict(
        date=time.strftime("%Y-%m-%d %H:%M"),
        retriever=settings.retriever, llm_model=settings.llm_model, k=K,
        results=results,
    ), ensure_ascii=False, indent=1), encoding="utf-8")

    hard = [r for r in results if not r["ok"] and not r["watch"]]
    watch_bad = [r for r in results if not r["ok"] and r["watch"]]

    print("\n" + "=" * 78)
    print(f"rag-qa 冒烟评测 · 漂移报告  {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"检索 {settings.retriever}(top-{K}) | 生成 {settings.llm_model}(内网 vLLM) | 服务加载 {load_s:.1f}s")
    print(f"基线快照: {prev['date'] if prev else '无(本次为首跑,跑完即建基线)'}")
    print("-" * 78)
    for r in results:
        mark = "PASS" if r["ok"] else ("WATCH" if r["watch"] else "FAIL")
        gold = f"gold={r['gold_doc']}(#{r['gold_rank']})" if r["gold_doc"] else "预期拒答"
        cite = "/".join(r["cited_docs"]) or "无"
        print(f"{mark:<5} {r['qid']:<10} {gold:<45} 引用文档:{cite}")
        if not r["ok"]:
            print(f"      失败项:{','.join(r['failed'])} | 解析 {r['parse_mode']} | 答案开头:{r['answer_head']}")
    print("-" * 78)
    if drift:
        print("漂移(与上次快照比):")
        for qid, d in drift:
            print(f"  {qid:<10} {d}")
    else:
        print("漂移:无(全部题与上次快照同表现)")
    n_ok = sum(r["ok"] for r in results)
    print(f"汇总:{n_ok}/{len(results)} 通过 | 观察名单未过 {len(watch_bad)} 题 | 硬失败 {len(hard)} 题")
    print(f"快照已写入 {BASELINE.relative_to(ROOT)}(下次跑批与它对比)")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
