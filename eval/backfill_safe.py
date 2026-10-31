"""回填历史 run 的「无法回答题安全判定」——不重跑生成，只对 refused=false 的答案调 judge。

用法:
    python -m eval.backfill_safe                       # 回填 eval/runs 下所有含 records 的 run
    python -m eval.backfill_safe <run_dir> [run_dir]   # 指定 run

输出:逐 run 的正确拒答率 / 安全作答率，以及每条被判定的答案与理由。不写文件、不改 records。
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import REPO_ROOT, RUNS_DIR, get_judge, judge_unanswerable, load_jsonl, utf8_stdout

CHUNKS_PATH = REPO_ROOT / "data" / "chunks" / "chunks.jsonl"


def _load_chunk_texts() -> dict[str, str]:
    if not CHUNKS_PATH.exists():
        return {}
    return {c["chunk_id"]: c["text"] for c in load_jsonl(CHUNKS_PATH)}


def _pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else "—"


def judge_run(run_dir: Path, judge, chunks: dict[str, str]) -> tuple[int, int, list[dict]]:
    """返回 (拒答数, 安全数, 判定明细)。安全数含拒答。"""
    records = load_jsonl(run_dir / "records.jsonl")
    un = [r for r in records if r["type"] == "unanswerable"]
    if not un:
        return 0, 0, []
    refused = [r for r in un if r["refused"]]
    judged: list[dict] = []
    safe = len(refused)
    for r in un:
        if r["refused"]:
            continue
        cited = [chunks.get(cid, "") for cid in r.get("cited_ids", [])]
        ok, reason = judge_unanswerable(judge[0], judge[1], r["question"], r["answer"], cited)
        judged.append({"qid": r["qid"], "safe": ok, "reason": reason, "answer": r["answer"]})
        safe += 1 if ok else 0
    return len(refused), safe, judged


def main() -> int:
    utf8_stdout()
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted(p for p in RUNS_DIR.iterdir() if (p / "records.jsonl").exists())
    judge = get_judge()
    chunks = _load_chunk_texts()
    print(f"judge: {judge[1]} | chunks: {len(chunks)}\n")
    for run_dir in paths:
        refused, safe, judged = judge_run(run_dir, judge, chunks)
        if not judged and refused == 0:
            print(f"{run_dir.name}: 无无法回答题记录,跳过")
            continue
        print(f"{run_dir.name}")
        print(f"  正确拒答(原口径) {refused}/40 = {_pct(refused, 40)}"
              f" | 安全(新口径) {safe}/40 = {_pct(safe, 40)}")
        for j in judged:
            mark = {True: "safe", False: "UNSAFE", None: "judge失败"}[j["safe"]]
            print(f"  - {j['qid']} [{mark}] {j['reason']}")
            print(f"    答案: {j['answer'][:160].replace(chr(10), ' ')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())