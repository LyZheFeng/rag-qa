"""Phase 2 开工冒烟：Chroma 可查 + vLLM 可生成（不依赖 app/，独立验证环境）。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from pipeline.store import get_collection

t0 = time.time()
col = get_collection(Path("data/chroma"), "fastapi_zh_v1")
print(f"[1] Chroma collection fastapi_zh_v1: {col.count()} 条 ({time.time()-t0:.1f}s)")

t0 = time.time()
from pipeline.embed import BgeM3Embedder

emb = BgeM3Embedder()
vec = emb.encode_queries(["如何声明请求体"])[0]
res = col.query(query_embeddings=[vec], n_results=2, include=["metadatas", "distances"])
for i, (meta, dist) in enumerate(zip(res["metadatas"][0], res["distances"][0])):
    print(f"  top{i+1} dist={dist:.3f} {meta['doc_name']} | {meta['section_path'][:40]}")
print(f"[2] 检索链路 OK ({time.time()-t0:.1f}s，含模型加载)")

t0 = time.time()
from openai import OpenAI

from pipeline.config import get_settings

s = get_settings()
client = OpenAI(base_url=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"), api_key=os.environ.get("LLM_API_KEY", "dummy"), timeout=60)
resp = client.chat.completions.create(
    model="Qwen3.8-27B",
    messages=[
        {"role": "system", "content": "只输出 JSON，格式 {\"ok\": true}"},
        {"role": "user", "content": "测试"},
    ],
    temperature=0,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
content = resp.choices[0].message.content
print(f"[3] LLM OK ({time.time()-t0:.1f}s): {content!r}")
print(f"    usage: {resp.usage.prompt_tokens}p/{resp.usage.completion_tokens}c tokens")
