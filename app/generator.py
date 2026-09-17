"""生成：编号上下文 → vLLM Qwen → 严格 JSON（answer/citations/refused）。

解析策略：失败重试 1 次（附纠正提示），再失败安全拒答（refused=true，
answer=固定提示语，citations 为空），parse_mode 记录走了哪条路。

流式（generate_stream）：LLM 仍输出严格 JSON，服务端边收边用 scan_answer
从半成品 JSON 里解出 answer 字段的前缀下发；显示是临时的，权威状态永远是
完整解析后的 outcome（retry 时下发 retry 项让前端清空重打）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
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


@dataclass
class StreamItem:
    """generate_stream 的产出：delta=可显示增量，retry=要求清空重打，outcome=权威终态。"""

    kind: str  # "delta" | "retry" | "outcome"
    text: str = ""
    outcome: GenerationOutcome | None = None


def _string_state(s: str, start: int, end: int) -> tuple[bool, int]:
    """扫描 [start, end)，返回 (是否停在字符串内, 花括号深度)。"""
    in_str = esc = False
    depth = 0
    for ch in s[start:end]:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return in_str, depth


def _decode_prefix(raw: str) -> str:
    r"""解码 answer 的原始片段：先砍掉尾部不完整转义（\ 或 \uXXX 不足 4 位）。"""
    m = re.search(r"\\(?:u[0-9a-fA-F]{0,3})?$", raw)
    safe = raw[: m.start()] if m else raw
    try:
        return json.loads('"' + safe + '"')
    except json.JSONDecodeError:  # answer 内出现裸控制字符等，最终会走 retry，此处原样给
        return safe


def scan_answer(buffer: str) -> tuple[str, bool] | None:
    """从累计原始输出抽顶层 "answer" 字段的已解码前缀。

    返回 (前缀, 是否已见闭合引号)；尚未定位到 answer 值则 None。
    与 extract_json 同口径：容忍 </think> 前缀，从首个 { 起扫。
    """
    if "</think>" in buffer:
        buffer = buffer.split("</think>")[-1]
    brace = buffer.find("{")
    if brace == -1:
        return None
    pos = brace
    while True:
        p = buffer.find('"answer"', pos)
        if p == -1:
            return None
        in_str, depth = _string_state(buffer, brace, p)
        colon = buffer.find(":", p + 8)
        after_key = buffer[p + 8 : colon].strip() if colon != -1 else ""
        if not in_str and depth == 1 and colon != -1 and after_key == "":
            q = colon + 1
            while q < len(buffer) and buffer[q] in " \t\r\n":
                q += 1
            if q >= len(buffer):
                return ("", False)  # 冒号后还没到值
            if buffer[q] != '"':
                return None  # answer 不是字符串（契约破坏），交给完整解析判死
            j, esc = q + 1, False
            while j < len(buffer):
                c = buffer[j]
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    return (_decode_prefix(buffer[q + 1 : j]), True)
                j += 1
            return (_decode_prefix(buffer[q + 1 : j]), False)
        pos = p + 8


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

    def _chat_stream(self, messages: list[dict]) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            max_tokens=self.max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

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

        # 两次解析失败：原文可能夹带围栏/思维链/解释文字，不可信，安全拒答而非照用
        return GenerationOutcome(
            AnswerSpec(answer="生成结果格式异常，无法给出可靠回答，请重试。", citations=[], refused=True),
            "fallback",
            raw,
        )

    def generate_stream(self, question: str, hits: list[Hit]) -> Iterator[StreamItem]:
        """流式版 generate：产出 delta/retry，最后产出一个 outcome（权威终态）。"""
        k = len(hits)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{build_context(hits)}\n\n问题：{question}"},
        ]
        outcome: GenerationOutcome | None = None
        raw = ""
        for attempt in (1, 2):
            if attempt == 2:
                yield StreamItem("retry")
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": RETRY_PROMPT},
                ]
            buffer, emitted = "", 0
            for piece in self._chat_stream(messages):
                buffer += piece
                got = scan_answer(buffer)
                if got is None:
                    continue
                prefix, _ = got
                if len(prefix) > emitted:
                    yield StreamItem("delta", text=prefix[emitted:])
                    emitted = len(prefix)
            spec = self._try_parse(buffer, k)
            if spec is not None:
                outcome = GenerationOutcome(spec, "json" if attempt == 1 else "retry", raw or buffer)
                break
            raw = buffer
        if outcome is None:
            outcome = GenerationOutcome(
                AnswerSpec(answer="生成结果格式异常，无法给出可靠回答，请重试。", citations=[], refused=True),
                "fallback",
                raw,
            )
        yield StreamItem("outcome", outcome=outcome)
