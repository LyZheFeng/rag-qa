"""v0.4-rewrite:LLM 多查询扩展 → 多路 hybrid 检索 → RRF 融合。

动机(v0.2 剩余误拒根因):9 道误拒中 7 道 gold 不在 top-5——问题表述与
gold chunk 词汇重合度低。多角度变体查询扩大召回覆盖。
改写 temperature=0(全链路确定性,评估可复现);变体差异来自"角度"而非采样。
LLM 调用失败/超时/解析失败 → 只用原问题,检索不中断。
"""

from __future__ import annotations

from .hybrid import rrf_fuse
from .schemas import Hit

REWRITE_PROMPT = """你在为 FastAPI 中文文档检索系统扩展查询。把用户问题改写成 3 个不同角度的检索查询,用于提高召回:
1. 同义改写:换一种自然说法,保留原意图
2. 关键词化:提取最可能出现在文档中的技术关键词(含英文名/API 名/代码标识符)
3. 场景补充:补上典型使用场景或相关概念词

只输出一个 JSON,禁止其他文字:
{{"variants": ["...", "...", "..."]}}

用户问题:{question}"""


class QueryRewriter:
    """原问题 → 最多 3 个变体(可能少于 3,失败返回空)。"""

    def __init__(self, client, model: str, max_tokens: int = 400):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    def rewrite(self, question: str) -> list[str]:
        from app.generator import extract_json

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(question=question)}],
                temperature=0,
                max_tokens=self.max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            obj = extract_json(resp.choices[0].message.content or "")
        except Exception:
            return []
        if not obj or not isinstance(obj.get("variants"), list):
            return []
        out = []
        for v in obj["variants"]:
            v = str(v).strip()
            if 4 <= len(v) <= 200 and v != question and v not in out:
                out.append(v)
        return out[:3]


class RewriteRetriever:
    """原问题 + 变体各取 hybrid top-N → 加权 RRF 融合 → top-k。

    约定:base 必须是 HybridRetriever(借用其 bm25.hit 构造完整 Hit)。
    原查询权重 orig_weight(默认 4,≈变体总和+1):变体共识只能抬升原排序 6~20 名的
    chunk,不能凭共识入侵 top-5——平权融合实测会稀释原查询排序(见 results.md v0.4)。
    """

    def __init__(self, base, rewrite_fn, candidates: int = 20, rrf_k: int = 60, orig_weight: float = 4.0):
        self.base = base
        self.rewrite_fn = rewrite_fn
        self.candidates = candidates
        self.rrf_k = rrf_k
        self.orig_weight = orig_weight

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        variants = self.rewrite_fn(query)
        if not variants:  # 改写失败 → 直接走 base 原生检索
            return self.base.retrieve(query, k=k)
        rank_lists = [[h.chunk_id for h in self.base.retrieve(q, k=self.candidates)] for q in [query] + variants]
        weights = [self.orig_weight] + [1.0] * len(variants)
        fused = rrf_fuse(*rank_lists, k=self.rrf_k, weights=weights)[:k]
        return [self.base.bm25.hit(cid, rank, score) for rank, (cid, score) in enumerate(fused, 1)]
