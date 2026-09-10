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
    """评估用 LLM client（出题 / judge），与生成同源同参。"""
    from openai import OpenAI

    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=120), s.llm_model


def chat_json(client, model: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.0) -> dict | None:
    """一次调用并抠 JSON；失败返回 None（调用方决定重试）。"""
    from app.generator import extract_json

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    text = resp.choices[0].message.content or ""
    obj = extract_json(text)
    return obj


def chat_text(client, model: str, prompt: str, max_tokens: int = 1500, temperature: float = 0.0) -> str:
    """一次调用返回纯文本(无检索对照等场景用)。"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
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
