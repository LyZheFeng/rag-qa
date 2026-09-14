"""mcp_server.py:走真实 stdio 子进程的协议级测试(项目 4 Day 24)。

用官方 SDK 的 in-process ClientSession 启动 `python -m app.mcp_server`
(与 MCP Inspector 相同的入口),覆盖:
- 三类原语的发现与调用(tools / resources / prompts);
- 检索结果「经 MCP 通道 vs 本地直连」逐字一致(MCP 不改工具语义的验证);
- 参数边界(top_k 超界)以 isError + 消息回传。

依赖真实索引(data/chroma + chunks.jsonl + 嵌入模型缓存),缺席时整文件跳过;
嵌入模型在测试进程与 server 子进程各加载一次(~7s/次),本文件预计 ~40s。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INDEX_READY = (
    (ROOT / "data" / "chroma" / "manifest.fastapi_zh_v1.json").exists()
    and (ROOT / "data" / "chunks" / "chunks.jsonl").exists()
)

pytestmark = pytest.mark.skipif(not INDEX_READY, reason="需要真实索引(chroma + chunks.jsonl)与嵌入模型缓存")


def run_over_stdio(scenario):
    """起一个真实 server 子进程跑完 scenario(coroutine)后关闭,返回其结果。"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=str(ROOT),
    )

    async def main():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session)

    return asyncio.run(main())


def test_protocol_surface():
    """tools/resources/prompts 可发现且内容与索引同源;top_k 边界以 isError 回传。"""

    async def scenario(s):
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == {"search"}
        props = tools["search"].input_schema["properties"]
        assert set(props) == {"query", "top_k"}

        uris = {str(r.uri) for r in (await s.list_resources()).resources}
        assert "rag-qa://corpus" in uris
        corpus = (await s.read_resource("rag-qa://corpus")).contents[0].text
        assert "1701 个 chunk" in corpus and "122 篇文档" in corpus
        assert "tutorial" in corpus  # 文档清单可见

        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert prompts == {"answer_with_citations"}
        rendered = (await s.get_prompt("answer_with_citations", {"question": "依赖注入怎么用"})).messages[0].content.text
        assert "依赖注入怎么用" in rendered and "拒答" in rendered and "[1]" in rendered

        bad = await s.call_tool("search", {"query": "边界测试", "top_k": 11})
        assert bad.is_error and "top_k" in bad.content[0].text

    run_over_stdio(scenario)


def test_search_parity_mcp_vs_local():
    """同一批 query:经 MCP search 与本地 retriever.retrieve+格式化逐字一致。"""
    from app.mcp_server import _format_hits
    from app.retriever import get_retriever

    queries = [
        ("怎么声明请求体模型", 3),
        ("allow_credentials", 2),
        ("后台任务 BackgroundTasks 怎么用", 5),
    ]

    async def scenario(s):
        retriever = get_retriever()  # 本地一侧,嵌入模型只加载一次
        for query, k in queries:
            res = await s.call_tool("search", {"query": query, "top_k": k})
            assert not res.is_error, res.content[0].text if res.content else "no content"
            assert res.content[0].text == _format_hits(retriever.retrieve(query, k=k)), query

    run_over_stdio(scenario)
