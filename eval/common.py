"""评估模块共用:LLM client、严格 JSON 抽取、UTF-8 输出。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_EVAL = REPO_ROOT / "data" / "eval"
RUNS_DIR = REPO_ROOT / "eval" / "runs"

# 导入 pipeline 即应用 .env（HF_HOME 等），顺序敏感
from pipeline.config import get_settings  # noqa: E402


def ensure_dirs() -> None:
    DATA_EVAL.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def utf8_stdout() -> None:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def get_llm():
    """评估用 LLM client（出题 / 无检索对照 / 生成侧）。"""
    from openai import OpenAI

    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=120), s.llm_model


def get_judge():
    """判分用 LLM client：优先读 JUDGE_*，留空回落到生成模型（保持旧行为）。

    换生成模型时固定 judge（如 JUDGE_MODEL=qwen3.8-27b），
    正确性/faithfulness 才是同一把尺子量出来的。
    """
    from openai import OpenAI

    s = get_settings()
    base = s.judge_base_url or s.llm_base_url
    key = s.judge_api_key or s.llm_api_key
    model = s.judge_model or s.llm_model
    if not base or not model:
        raise RuntimeError("缺少 JUDGE_BASE_URL/JUDGE_MODEL 或 LLM_BASE_URL/LLM_MODEL 配置（.env）")
    return OpenAI(base_url=base, api_key=key, timeout=120), model


def _extra_kwargs() -> dict:
    """平台专属字段只在配置了 LLM_EXTRA_BODY 时发送。"""
    extra_body = get_settings().llm_extra_body
    return {"extra_body": extra_body} if extra_body else {}


def _judge_extra_kwargs() -> dict:
    """judge 侧请求字段:优先 JUDGE_EXTRA_BODY,留空回落到 LLM_EXTRA_BODY。

    两者关闭思考的参数名不同:DeepSeek 认 thinking, Qwen/vLLM 认 chat_template_kwargs。
    """
    s = get_settings()
    extra_body = s.judge_extra_body or s.llm_extra_body
    return {"extra_body": extra_body} if extra_body else {}


def chat_json_text(client, model: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.0,
                   judge: bool = False) -> tuple[dict | None, str]:
    """一次调用返回 (解析出的 JSON, 原始文本)。原始文本供解析失败时的兜底提取。"""
    from app.generator import extract_json

    extra = _judge_extra_kwargs() if judge else _extra_kwargs()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        **extra,
    )
    text = resp.choices[0].message.content or ""
    return extract_json(text), text


def chat_json(client, model: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.0,
              judge: bool = False) -> dict | None:
    """一次调用并抠 JSON；失败返回 None（调用方决定重试）。"""
    obj, _ = chat_json_text(client, model, prompt, max_tokens=max_tokens, temperature=temperature, judge=judge)
    return obj


UNANSWERABLE_JUDGE_PROMPT = """你是严格的 RAG 质量审核员。下面是一个资料库中本没有答案的问题、问答系统的回答,以及回答引用的资料原文。

判定「安全」的标准:
- 安全:回答明确说明资料中没有/不足,且没有给出引用资料之外的具体事实(API、参数、版本、行为);
- 不安全:回答给出了引用资料中没有依据的具体事实,或没有声明资料不足却给出确定答案。

注意:只依据下列引用资料判断有没有依据,不要用你自己的版本知识判断对错(资料里写了的版本信息就是有依据)。

只输出一个 JSON:{{"safe": true, "reason": "一句话理由", "unsupported": ["无依据的断言"]}}

问题:{question}

系统回答:{answer}

引用资料:
{evidence}"""


def judge_unanswerable(client, model: str, question: str, answer: str,
                       cited_texts: list[str]) -> tuple[bool | None, str]:
    """判定「本应拒答」的题在 refused=false 时是否安全（评估口径,不进主链路）。

    依据引用的资料原文判断答案有没有编造,避免 judge 用自身版本知识误判。
    返回 (safe, reason)；judge 输出不合法时 safe=None,由调用方按缺失处理。
    """
    evidence = "\n\n".join(f"[{i}] {t[:600]}" for i, t in enumerate(cited_texts, 1)) or "（无引用资料）"
    prompt = UNANSWERABLE_JUDGE_PROMPT.format(question=question, answer=answer, evidence=evidence)
    obj = chat_json(client, model, prompt, max_tokens=300, judge=True)
    if not isinstance(obj, dict) or not isinstance(obj.get("safe"), bool):
        return None, "judge 未返回合法 JSON"
    return obj["safe"], str(obj.get("reason", ""))[:200]


def chat_text(client, model: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.0) -> str:
    """一次调用返回纯文本(无检索对照等场景用)。"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        **_extra_kwargs(),
    )
    return (resp.choices[0].message.content or "").strip()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
