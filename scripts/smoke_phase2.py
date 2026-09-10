"""Phase 2 端到端冒烟：5 个手工问题走完整链路（检索 → 生成 → 引用/拒答）+ 延迟。

用法：.venv/Scripts/python.exe scripts/smoke_phase2.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

QUESTIONS = [
    "如何在 FastAPI 中声明请求体？请说明 Pydantic 模型的基本用法。",
    "依赖注入中 Depends 怎么用？举一个简单的例子。",
    "如何添加自定义异常处理器返回统一的错误格式？",
    "后台任务 BackgroundTasks 怎么用？",
    "FastAPI 官方文档中如何配置 gRPC 支持？",  # 预期拒答：语料无此内容
]


def main() -> None:
    from app.service import get_service

    t_start = time.time()
    print("加载服务（嵌入模型 + LLM 客户端）...")
    svc = get_service()
    print(f"  就绪 {time.time() - t_start:.1f}s\n" + "=" * 72)

    latencies = []
    for i, q in enumerate(QUESTIONS, 1):
        resp = svc.ask(q)
        latencies.append(resp.latency)
        print(f"\n【Q{i}】{q}")
        flag = "拒答" if resp.refused else f"引用 {resp.cited and '/'.join(str(h.index) for h in resp.cited) or '无'}"
        print(f"  → {flag} | 解析 {resp.parse_mode} | "
              f"检索 {resp.latency.retrieve_ms}ms + 生成 {resp.latency.generate_ms}ms = {resp.latency.total_ms}ms")
        print(f"  答案：{resp.answer[:300]}")
        for h in resp.cited:
            print(f"    [{h.index}] {h.doc_name} > {h.section_path}（相似度 {h.score:.3f}）")
        print("-" * 72)

    n = len(latencies)
    print(
        f"\n汇总：{n} 问 | 检索均值 {sum(l.retrieve_ms for l in latencies)/n:.0f}ms | "
        f"生成均值 {sum(l.generate_ms for l in latencies)/n:.0f}ms | "
        f"端到端均值 {sum(l.total_ms for l in latencies)/n:.0f}ms | "
        f"最大 {max(l.total_ms for l in latencies)}ms"
    )


if __name__ == "__main__":
    main()
