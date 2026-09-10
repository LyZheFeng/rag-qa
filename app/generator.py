"""生成：编号上下文 → vLLM Qwen → 严格 JSON（answer/citations/refused）。

解析策略：失败重试 1 次（附纠正提示），再失败降级纯文本（answer=原文，
citations=[]，refused=False），parse_mode 记录走了哪条路。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from .schemas import AnswerSpec, Hit

SYSTEM_PROMPT = """你是 FastAPI 中文文档的问答助手，只依据用户提供的编号资料回答。

规则：
1. 优先依据资料回答，答案中在对应句子末尾标注资料编号，如 [1] 或 [2][3]；代码示例直接保留资料中的代码。
2. 资料不足以回答问题时必须拒答：refused=true，answer 用一两句话说明缺少什么信息，citations 为空数组。禁止编造。
3. 只输出一个 JSON 对象，禁止输出任何其他文字、解释或代码围栏：
   {"answer": "...", "citations": [1, 2], "refused": false}
4. citations 只包含 answer 实际用到的资料编号（1 起的整数）。"""

RETRY_PROMPT = (
    "你上一次的输出不是合法的单个 JSON 对象。请重新作答，"
    '只输出一个 JSON：{"answer": "...", "citations": [编号列表], "refused": 布尔值}，不要包含任何其他文字。'
)

MAX_TOKENS = 1500


def build_context(hits: list[Hit]) -> str:
    """编号资料块，编号与 Hit.index 一致（LLM 引用与溯源共用）。"""
    blocks = []
    for h in hits:
        blocks.append(f"[{h.index}] 来源：{h.doc_name} > {h.section_path}\n{h.text}")
    return "资料：\n" + "\n\n".join(blocks)


def extract_json(text: str) -> dict | None:
    """从 LLM 输出里抠 JSON：剥思维链/围栏/前后缀，取首个 { 到末个 }。"""
    if "</think>" in text:  # enable_thinking 失效时的兜底
        text = text.split("</think>")[-1]
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def validate_citations(citations: list, k: int) -> list[int]:
    """只留 [1, k] 内的整数，去重排序。"""
    valid = {c for c in citations if isinstance(c, int) and not isinstance(c, bool) and 1 <= c <= k}
    return sorted(valid)


@dataclass
class GenerationOutcome:
    spec: AnswerSpec
    parse_mode: str  # "json" | "retry" | "fallback"
    raw: str  # 首次原始输出（排查用）


class LLMGenerator:
    def __init__(self, client: OpenAI, model: str, max_tokens: int = MAX_TOKENS):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    @classmethod
    def from_settings(cls) -> "LLMGenerator":
        from pipeline.config import get_settings

        s = get_settings()
        if not (s.llm_base_url and s.llm_model):
            raise RuntimeError("缺少 LLM_BASE_URL / LLM_MODEL 配置（.env）")
        return cls(
            OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=60),
            s.llm_model,
        )

    def _chat(self, messages: list[dict]) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=self.max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return resp.choices[0].message.content or ""

    def _try_parse(self, text: str, k: int) -> AnswerSpec | None:
        obj = extract_json(text)
        if obj is None:
            return None
        # 引用清洗必须在 pydantic 之前做：list[int] 会把 true 强转成 1
        if "citations" in obj and isinstance(obj["citations"], list):
            obj["citations"] = validate_citations(obj["citations"], k)
        try:
            spec = AnswerSpec(**obj)
        except Exception:
            return None
        if spec.refused:
            spec.citations = []
        return spec

    def generate(self, question: str, hits: list[Hit]) -> GenerationOutcome:
        k = len(hits)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{build_context(hits)}\n\n问题：{question}"},
        ]
        raw = self._chat(messages)

        spec = self._try_parse(raw, k)
        if spec is not None:
            return GenerationOutcome(spec, "json", raw)

        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": RETRY_PROMPT},
        ]
        raw2 = self._chat(messages)
        spec = self._try_parse(raw2, k)
        if spec is not None:
            return GenerationOutcome(spec, "retry", raw)

        # 降级纯文本：答案照用，引用置空（Phase 2 基线策略）
        return GenerationOutcome(AnswerSpec(answer=raw2.strip(), citations=[], refused=False), "fallback", raw)
