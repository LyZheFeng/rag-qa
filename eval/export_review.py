"""导出测试集审核文件(介入点 C):给用户逐题确认的 markdown。

用户可在文件中把要删除的题目标 `x`,我回收后生成正式 questions.jsonl。
"""

from __future__ import annotations

import sys
from collections import Counter

from .common import DATA_EVAL, load_jsonl, utf8_stdout

TYPE_LABEL = {"fact": "事实", "reasoning": "推理", "unanswerable": "无法回答"}


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def main() -> None:
    utf8_stdout()
    questions = load_jsonl(DATA_EVAL / "questions.jsonl")
    counts = Counter(q["type"] for q in questions)

    lines = [
        "# 测试集审核(介入点 C)",
        "",
        f"> 共 {len(questions)} 题:事实 {counts['fact']} / 推理 {counts['reasoning']} / 无法回答 {counts['unanswerable']}。",
        "> 已经过自动预筛:格式校验、gold chunk 一致性复核(可答题)、检索复核(无法回答题)。",
        "> **请逐题过目**:要删除的题把行首编号改成 `x`(如 `x|F001|`);要改的可直接改问题文本。",
        "> 重点确认:① 问题表述自然无歧义 ② 参考答案正确 ③ 无法回答题确实语料无答案(红线)。",
        "",
    ]

    for qtype in ("fact", "reasoning", "unanswerable"):
        items = [q for q in questions if q["type"] == qtype]
        lines += [f"## {TYPE_LABEL[qtype]}题({len(items)} 道)", ""]
        if qtype == "unanswerable":
            lines += ["| 编号 | 问题 | 出题理由(为何语料覆盖不到) | 复核结论 |", "|---|---|---|---|"]
        else:
            lines += ["| 编号 | 问题 | 参考答案 | 依据(gold chunk) | 支撑原句 |", "|---|---|---|---|---|"]
        for i, q in enumerate(items, 1):
            tag = q["qid"].split("-")[0][:1].upper() if qtype != "unanswerable" else "U"
            num = f"{tag}{i:03d}"
            if qtype == "unanswerable":
                lines.append(f"| {num} | {esc(q['question'])} | {esc(q.get('explanation'))} | 检索 top5 无答案(judge 复核通过) |")
            else:
                gold = f"{q['gold_doc']} · {esc(q['gold_section'])}"
                lines.append(f"| {num} | {esc(q['question'])} | {esc(q['answer'])} | {gold} | {esc(q.get('quote'))} |")
        lines.append("")

    out = DATA_EVAL / "review_questions.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {out}({len(questions)} 题)")


if __name__ == "__main__":
    sys.exit(main())
