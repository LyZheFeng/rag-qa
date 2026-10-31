"""每轮评估跑完后自动记账:等 summary.json 出现 → 追加一条 Markdown 记录到 eval/results-deepseek.md。

用法(每轮一个进程,互相独立):
    python eval/record_run.py v0.6-ds-qwen-r1

设计:
- 轮询该版本对应的 run 目录(30s 一次,最长 4h),summary.json 落地即记一条;
- 记录内容全部来自 records.jsonl 实算,不读 README/不手填;
- 幂等:文件里已有该 run 目录名就跳过,重复启动不会写重;
- 三轮各自的均值±波动由 record_all.py 在全部结束后汇总。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "eval" / "runs"
OUT = ROOT / "eval" / "results-deepseek.md"


def _records(run_dir: Path) -> list[dict]:
    p = run_dir / "records.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _fmt(rate: float | None) -> str:
    return "—" if rate is None else f"{rate:.1%}"


def _finished_at(run_dir: Path):
    """实际完成时间:以 records.jsonl 最后写入为准。

    record_run 可能事后补跑(两轮一起记账),用 datetime.now() 会把完成时间记成记账时间。
    """
    for name in ("records.jsonl", "summary.json"):
        p = run_dir / name
        if p.exists():
            return datetime.fromtimestamp(p.stat().st_mtime)
    return datetime.now()


def build_block(version: str) -> str | None:
    dirs = sorted(RUNS.glob(f"{version}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dirs:
        return None
    run_dir = dirs[0]
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return None

    s = json.loads(summary_path.read_text(encoding="utf-8"))
    recs = _records(run_dir)
    answerable = [r for r in recs if r["type"] in ("fact", "reasoning")]
    unans = [r for r in recs if r["type"] == "unanswerable"]
    refused_ans = sum(1 for r in answerable if r["refused"])
    refused_unans = sum(1 for r in unans if r["refused"])
    zeros = sum(1 for r in answerable if r.get("correctness") == 0)
    scores = [r["correctness"] for r in answerable if r.get("correctness") is not None]

    lines = [
        f"## {version}",
        "",
        f"- 运行目录:`{run_dir.name}`",
        f"- 完成时间:{_finished_at(run_dir).strftime('%Y-%m-%d %H:%M')}",
        f"- 模型:生成 `{s.get('llm_model', '—')}` / 判分 `{s.get('judge_model', '—')}`",
        f"- 样本:{s.get('n')} 题（可答 {len(answerable)} / 无法回答 {len(unans)}）",
        f"- **正确性 {s.get('正确性')}**（事实 {s.get('正确性_事实')} / 推理 {s.get('正确性_推理')}）"
        f"，参与打分 {len(scores)} 条，judge 解析失败 {zeros} 条",
        f"- 无检索对照:{s.get('正确性_无检索对照')}",
        f"- 误拒率 {_fmt(s.get('误拒率(可答题拒答)'))}（{refused_ans}/{len(answerable)}）"
        f"；正确拒答率 {_fmt(s.get('正确拒答率(无法答题)'))}（{refused_unans}/{len(unans)}）",
        f"- 检索:recall@5 chunk {s.get('recall@5_chunk')} / doc {s.get('recall@5_doc')}，MRR {s.get('MRR')}",
        f"- faithfulness {s.get('faithfulness')}（n={s.get('faithfulness_n')}）",
        f"- 跑批异常:{s.get('errors', 0)}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python eval/record_run.py <version>")
        raise SystemExit(2)
    version = sys.argv[1]
    deadline = time.time() + 4 * 3600
    while time.time() < deadline:
        block = build_block(version)
        if block is not None:
            existing = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
            if version in existing:
                print(f"{version} 已记录,跳过")
                return
            header = "" if OUT.exists() else "# DeepSeek 答题 / Qwen 判题 · 逐轮记录\n\n> 由 eval/record_run.py 自动生成,数字均从 records.jsonl 实算。\n\n"
            with OUT.open("a", encoding="utf-8") as f:
                f.write(header + block)
            print(block)
            return
        time.sleep(30)
    print(f"{version} 等待超时(4h),未记录")


if __name__ == "__main__":
    main()