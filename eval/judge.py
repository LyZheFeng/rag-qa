"""LLM judge:题目-资料一致性、无法回答复核、正确性 1~5、faithfulness 拆 claim。

全部 temperature=0(评估纪律)。judge 与生成同模型(Qwen3.8-27B),
拆 claim + 明确评分锚点缓解自评宽松。
"""

from __future__ import annotations

from .common import chat_json

GOLD_CHECK_PROMPT = """判断一道题的参考答案是否能由给定资料支持。

资料(来自文档 {doc} > {section}):
{chunk}

问题:{question}
参考答案:{answer}

判定标准:资料必须实际包含答案所需信息(允许措辞不同、允许推理题的结论由资料推出);资料只沾边但缺关键信息判 false。
只输出一个 JSON:{{"supported": true/false, "reason": "一句话"}}"""


UNANSWERABLE_CHECK_PROMPT = """判断下面检索到的资料是否真的能回答该问题。

问题:{question}

检索到的资料:
{chunks}

判定标准:任何一条资料实际包含该问题的答案即 true;只有相关术语、相关主题但无答案判 false。
只输出一个 JSON:{{"answerable": true/false, "reason": "一句话"}}"""


CORRECTNESS_PROMPT = """你是严格的评分员。根据参考答案给学生答案打分(1~5 整数)。

问题:{question}
参考答案:{reference}
学生答案:{answer}

评分标准:
5 = 完全正确且关键点完整
4 = 正确但欠完整或表述含糊
3 = 部分正确,有小错误或遗漏关键点
2 = 大部分错误
1 = 完全错误、答非所问、或声称无法回答而拒答

只输出一个 JSON:{{"score": 1, "reason": "一句话理由"}}"""


FAITH_PROMPT = """你是忠实性审核员。把答案拆成独立的事实声明,逐条判断是否被给定资料支持。

资料:
{chunks}

答案:{answer}

要求:
1. 每条声明必须可独立判断真假;代码块按其语义算作一条
2. 声明与资料措辞不同但事实一致 = 支持;资料未提及或与资料矛盾 = 不支持
3. 只输出一个 JSON:{{"claims": [{{"claim": "...", "supported": true/false}}]}}
答案至少拆 1 条,最多 8 条(只拆主要声明)。"""


def gold_supported(client, model: str, q: dict, chunk_text: str) -> tuple[bool, str]:
    obj = chat_json(
        client,
        model,
        GOLD_CHECK_PROMPT.format(
            doc=q.get("gold_doc") or "",
            section=q.get("gold_section") or "",
            chunk=chunk_text,
            question=q["question"],
            answer=q.get("answer") or "",
        ),
        max_tokens=300,
    )
    if not obj or not isinstance(obj.get("supported"), bool):
        return False, "parse_fail"
    return obj["supported"], str(obj.get("reason", ""))[:120]


def unanswerable_check(client, model: str, question: str, hits: list) -> tuple[bool, str]:
    chunks = "\n\n".join(
        f"[{h.index}] 来源:{h.doc_name} > {h.section_path}\n{h.text[:600]}" for h in hits
    )
    obj = chat_json(client, model, UNANSWERABLE_CHECK_PROMPT.format(question=question, chunks=chunks), max_tokens=300)
    if not obj or not isinstance(obj.get("answerable"), bool):
        return True, "parse_fail(按可疑丢弃)"  # 复核失败按"语料可能有答案"处理,宁弃勿留
    return obj["answerable"], str(obj.get("reason", ""))[:120]


def correctness(client, model: str, question: str, reference: str, answer: str) -> tuple[int, str]:
    obj = chat_json(
        client,
        model,
        CORRECTNESS_PROMPT.format(question=question, reference=reference, answer=answer),
        max_tokens=300,
    )
    if not obj:
        return 0, "parse_fail"
    score = obj.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
        return 0, "bad_score"
    return score, str(obj.get("reason", ""))[:120]


def faithfulness_claims(client, model: str, answer: str, cited_texts: list[str]) -> list[dict] | None:
    chunks = "\n\n".join(f"[{i+1}] {t[:800]}" for i, t in enumerate(cited_texts))
    obj = chat_json(client, model, FAITH_PROMPT.format(chunks=chunks, answer=answer), max_tokens=1200)
    if not obj or not isinstance(obj.get("claims"), list) or not obj["claims"]:
        return None
    claims = []
    for c in obj["claims"][:8]:
        if isinstance(c, dict) and isinstance(c.get("supported"), bool) and c.get("claim"):
            claims.append({"claim": str(c["claim"])[:200], "supported": c["supported"]})
    return claims or None
