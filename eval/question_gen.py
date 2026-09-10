"""Phase 3 出题:分层抽 chunk → Qwen 生成事实/推理/无法回答三类题。

- 出题是数据构造,不是评估:temperature 取 0.7/0.9 换取多样性(评估跑批才严格 0)
- 事实/推理题一 chunk 一题,单 chunk 必须自足作答
- 无法回答题:给语料主题清单,要求出"用户会问但文档没覆盖"的问题,预筛阶段检索复核
- 断点续跑:按类型计数,只补缺口
"""

from __future__ import annotations

import sys

from .common import DATA_EVAL, REPO_ROOT, append_jsonl, chat_json, ensure_dirs, get_llm, load_jsonl, utf8_stdout
from .sampling import eligible_chunks, stratified_sample

SEED = 42

# 目标本数(含预筛损耗冗余):最终 100/60/40
TARGETS = {"fact": 120, "reasoning": 72, "unanswerable": 48}

# 无法回答题的方向轮换,强制主题分散(temperature 之外的确定性多样性)
NOANSWER_HINTS = [
    "部署与运维(服务器、worker、容器、反向代理)",
    "数据库与 ORM(SQLAlchemy、迁移工具)",
    "性能与压测(基准工具、profiling、缓存)",
    "监控、日志与告警(链路追踪、指标)",
    "生态集成(GraphQL、gRPC、消息队列、WebSocket 之外的实时方案)",
    "认证生态细节(OAuth2 之外:JWT 库选型、session、第三方登录)",
    "测试策略之外的工程化(mock、CI、契约测试)",
    "版本迁移与兼容(Python/FastAPI 版本升级、弃用政策)",
    "前端/客户端集成(CORS 之外的跨域、静态资源、模板之外的方案)",
    "并发与后台任务之外的可扩展性(分布式任务、限流)",
]

FACT_PROMPT = """你是 FastAPI 中文文档 RAG 系统的测试集出题人。基于下面这段资料出一道【事实型】问题。

要求:
1. 问题必须能仅凭这段资料直接回答,答案(含代码细节)在资料中明确存在
2. 问题要自然,像真实用户会问的;禁止出现"这段资料""文档""上文"等字样
3. 优先出用法、行为、参数、配置、示例相关;不出"XX 的定义是什么"式背诵题
4. 标准答案简明扼要,可含短代码,必须完全取自资料
5. 只输出一个 JSON,禁止任何其他文字:
{{"question": "...", "answer": "...", "quote": "资料中支撑答案的关键原句"}}

资料(来自文档 {doc} > {section}):
{text}"""

REASON_PROMPT = """你是 FastAPI 中文文档 RAG 系统的测试集出题人。基于下面这段资料出一道【推理型】问题。

要求:
1. 答案不能是资料原文照抄,需要理解、对比、综合或推断(如"为什么…""A 和 B 有什么区别""如果…会怎样""什么场景该用哪个")
2. 但答案必须能仅凭这段资料推出,不需要资料外的知识
3. 问题要自然,像真实用户会问的;禁止出现"这段资料""文档""上文"等字样
4. 标准答案给出推理结论与依据
5. 只输出一个 JSON,禁止任何其他文字:
{{"question": "...", "answer": "...", "quote": "资料中支撑推理的关键原句"}}

资料(来自文档 {doc} > {section}):
{text}"""

NOANSWER_PROMPT = """你在为 FastAPI 官方中文文档的 RAG 问答系统构造"无法回答"测试题。

语料只覆盖以下主题:
{topics}

请出一道 FastAPI 用户真实会问、但上述主题【没有覆盖】的问题。方向提示:{hint}

要求:
1. 问题看起来"应该在 FastAPI 文档里有答案",足以诱使系统强行作答
2. 必须与 FastAPI 相关,不出无关领域问题;不题目材里其实覆盖的主题
3. 只输出一个 JSON,禁止任何其他文字:
{{"question": "...", "explanation": "为什么语料覆盖不到,一句话"}}"""


def normalize(q: str) -> str:
    """去空白与标点后的小写规范化,用于粗去重。"""
    import re

    return re.sub(r"[\s,。?!?!,.;；:'\"'\"()《》<>【】\[\]-]+", "", q).lower()


def build_topic_list(chunks: list[dict]) -> str:
    docs = sorted({c["doc_name"][: -len(".md")].replace("/", " / ") for c in chunks})
    return "\n".join(f"- {d}" for d in docs)


def gen_answerable(client, model: str, qtype: str, chunk: dict) -> dict | None:
    prompt = (FACT_PROMPT if qtype == "fact" else REASON_PROMPT).format(
        doc=chunk["doc_name"], section=chunk["section_path"], text=chunk["text"]
    )
    obj = chat_json(client, model, prompt, temperature=0.7)
    if not obj:
        return None
    q, a = str(obj.get("question", "")).strip(), str(obj.get("answer", "")).strip()
    quote = str(obj.get("quote", "")).strip()
    if len(q) < 8 or len(q) > 150 or len(a) < 4:
        return None
    return {
        "type": qtype,
        "question": q,
        "answer": a,
        "quote": quote,
        "gold_chunk_id": chunk["chunk_id"],
        "gold_doc": chunk["doc_name"],
        "gold_section": chunk["section_path"],
    }


def gen_unanswerable(client, model: str, hint: str, topics: str) -> dict | None:
    prompt = NOANSWER_PROMPT.format(topics=topics, hint=hint)
    obj = chat_json(client, model, prompt, temperature=0.9)
    if not obj:
        return None
    q = str(obj.get("question", "")).strip()
    explanation = str(obj.get("explanation", "")).strip()
    if len(q) < 8 or len(q) > 150:
        return None
    return {
        "type": "unanswerable",
        "question": q,
        "answer": None,
        "explanation": explanation,
        "gold_chunk_id": None,
        "gold_doc": None,
        "gold_section": None,
    }


def main() -> None:
    utf8_stdout()
    ensure_dirs()

    chunks_path = REPO_ROOT / "data" / "chunks" / "chunks.jsonl"
    chunks = load_jsonl(chunks_path)
    raw_path = DATA_EVAL / "questions_raw.jsonl"
    existing = load_jsonl(raw_path)
    have = {t: sum(1 for r in existing if r["type"] == t) for t in TARGETS}

    client, model = get_llm()
    seen = {normalize(r["question"]) for r in existing}

    # 可答题:一次抽齐 fact+reasoning 的 chunk 池,互不重复
    pool = eligible_chunks(chunks)
    need_total = max(0, TARGETS["fact"] - have["fact"]) + max(0, TARGETS["reasoning"] - have["reasoning"])
    sample = stratified_sample(pool, need_total, SEED) if need_total else []

    counters = dict(have)
    fails = 0
    for chunk in sample:
        qtype = "fact" if counters["fact"] < TARGETS["fact"] else "reasoning"
        rec = None
        for _ in range(2):  # 解析失败/重复问题各给一次机会
            rec = gen_answerable(client, model, qtype, chunk)
            if rec and normalize(rec["question"]) not in seen:
                break
            rec = None
        if rec is None:
            fails += 1
            continue
        rec["qid"] = f"{qtype[:4]}-{counters[qtype] + 1:03d}"
        counters[qtype] += 1
        seen.add(normalize(rec["question"]))
        append_jsonl(raw_path, [rec])
        print(f"[{counters[qtype]}/{TARGETS[qtype]}] {qtype}: {rec['question'][:40]}", flush=True)

    topics = build_topic_list(chunks)
    i = counters["unanswerable"]
    while i < TARGETS["unanswerable"]:
        hint = NOANSWER_HINTS[i % len(NOANSWER_HINTS)]
        rec = None
        for _ in range(2):
            rec = gen_unanswerable(client, model, hint, topics)
            if rec and normalize(rec["question"]) not in seen:
                break
            rec = None
        if rec is None:
            fails += 1
            hint = NOANSWER_HINTS[(i + fails) % len(NOANSWER_HINTS)]
            if fails > 20:
                break
            continue
        i += 1
        rec["qid"] = f"unans-{i:03d}"
        counters["unanswerable"] = i
        seen.add(normalize(rec["question"]))
        append_jsonl(raw_path, [rec])
        print(f"[{i}/{TARGETS['unanswerable']}] unanswerable: {rec['question'][:40]}", flush=True)

    print(f"\n完成。当前计数: {counters},生成失败 {fails} 次,文件: {raw_path}")


if __name__ == "__main__":
    sys.exit(main())
