"""mcp_server.py 的协议级测试(项目 4 Day 24)。

首项为完全 mock 的协议 smoke:真实 stdio 子进程跑 tests/mcp_stub_entry.py
(真 server + 假 retriever),不需要嵌入模型/索引,CI 常跑——覆盖三类原语
发现与调用、top_k 边界、基础设施/未预期异常的脱敏回传、无索引时 corpus 降级。

随后两项走真实 stdio 子进程(真实入口 `python -m app.mcp_server`,依赖
真实索引与嵌入模型,缺席时跳过):
- 三类原语的发现与调用(tools / resources / prompts),corpus 统计与 manifest 同源
  (期望值从 manifest/chunks.jsonl 现算,不硬编码,索引重建后测试仍成立);
- 检索结果「经 MCP 通道 vs 本地直连」逐字一致(MCP 不改工具语义的验证)。

末三项为进程内测试(不需要真实索引):corpus resource 的降级路径
(manifest 缺失/损坏/编码错误、chunks 不可读/编码损坏、非对象 JSON 行、
非法 doc_name 时不抛错)、缓存随索引重建失效,以及 search 的异常边界
(ToolError 转换 + 日志留底)。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INDEX_READY = (
    (ROOT / "data" / "chroma" / "manifest.fastapi_zh_v1.json").exists()
    and (ROOT / "data" / "chunks" / "chunks.jsonl").exists()
)

needs_index = pytest.mark.skipif(not INDEX_READY, reason="需要真实索引(chroma + chunks.jsonl)与嵌入模型缓存")


def run_over_stdio(scenario, *server_args):
    """起一个真实 server 子进程跑完 scenario(coroutine)后关闭,返回其结果。

    默认入口 `python -m app.mcp_server`;可传替代入口(如 mcp_stub_entry.py)。
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=list(server_args) if server_args else ["-m", "app.mcp_server"],
        cwd=str(ROOT),
    )

    async def main():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await scenario(session)

    return asyncio.run(main())


def test_protocol_smoke_without_index():
    """完全 mock 的协议 smoke:真实 stdio 子进程 + 假 retriever。

    不需要嵌入模型/索引,CI 常跑:三类原语发现与调用、top_k 边界、
    基础设施异常与未预期异常的脱敏回传,以及无索引时 corpus 降级可读。
    """

    async def scenario(s):
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == {"search"}
        assert set(tools["search"].input_schema["properties"]) == {"query", "top_k"}

        uris = {str(r.uri) for r in (await s.list_resources()).resources}
        assert "rag-qa://corpus" in uris
        corpus = (await s.read_resource("rag-qa://corpus")).contents[0].text
        assert "检索模式:" in corpus  # 无索引时也能读(降级为统计说明)

        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert prompts == {"answer_with_citations"}
        rendered = (await s.get_prompt("answer_with_citations", {"question": "smoke"})).messages[0].content.text
        assert "smoke" in rendered and "[1]" in rendered

        res = await s.call_tool("search", {"query": "smoke", "top_k": 2})
        assert not res.is_error, res.content[0].text if res.content else "no content"
        assert "命中:smoke" in res.content[0].text and res.content[0].text.count("来源:") == 2

        bad = await s.call_tool("search", {"query": "边界", "top_k": 11})
        assert bad.is_error and "top_k" in bad.content[0].text

        infra = await s.call_tool("search", {"query": "boom"})
        assert infra.is_error and "检索暂不可用" in infra.content[0].text
        assert "fake" not in infra.content[0].text  # 内部路径不回传

        weird = await s.call_tool("search", {"query": "weird"})
        assert weird.is_error and "检索内部错误" in weird.content[0].text
        assert "internal detail" not in weird.content[0].text

        leak = await s.call_tool("search", {"query": "leak"})
        assert leak.is_error and "检索内部错误" in leak.content[0].text
        assert "secrets" not in leak.content[0].text and "10.0.0.1" not in leak.content[0].text

    run_over_stdio(scenario, str(ROOT / "tests" / "mcp_stub_entry.py"))


@needs_index
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
        from pipeline.config import get_settings
        from pipeline.manifest import manifest_path

        cfg = get_settings()
        m = json.loads(manifest_path(cfg.chroma_dir, cfg.collection).read_text(encoding="utf-8"))
        doc_names = set()
        with open(cfg.chunks_path, encoding="utf-8") as f:
            for line in f:
                name = json.loads(line).get("doc_name")
                if name:
                    doc_names.add(name)
        assert f"{m['chunk_count']} 个 chunk" in corpus
        assert f"{len(doc_names)} 篇文档" in corpus
        assert "tutorial" in corpus  # 文档清单可见

        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert prompts == {"answer_with_citations"}
        rendered = (await s.get_prompt("answer_with_citations", {"question": "依赖注入怎么用"})).messages[0].content.text
        assert "依赖注入怎么用" in rendered and "拒答" in rendered and "[1]" in rendered

        bad = await s.call_tool("search", {"query": "边界测试", "top_k": 11})
        assert bad.is_error and "top_k" in bad.content[0].text

    run_over_stdio(scenario)


@needs_index
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


def _stub_settings(tmp_path: Path):
    """绕开 .env:把 _corpus_stats 指向 tmp_path 里的假索引。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        retriever="hybrid",
        embed_model="BAAI/bge-m3",
        collection="t1",
        chroma_dir=tmp_path,
        chunks_path=tmp_path / "chunks.jsonl",
    )


class _FlakyChunksReader:
    """读第一行后抛 OSError,模拟 chunks 读取中途的磁盘/IO 故障。"""

    def __init__(self, fh):
        self._fh = fh

    def __iter__(self):
        for i, line in enumerate(self._fh):
            if i > 0:
                raise OSError("device not ready(模拟)")
            yield line

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)


def test_corpus_resource_degrades_instead_of_raising(tmp_path, monkeypatch):
    """manifest 缺失/损坏/缺字段、chunks 不可读时,resource 返回降级说明而非裸异常。"""
    from app import mcp_server

    monkeypatch.setattr(mcp_server, "get_settings", lambda: _stub_settings(tmp_path))

    # 两者全缺:两条降级说明,不抛错
    text = mcp_server._corpus_stats()
    assert "manifest 不存在" in text and "chunks 文件不可读" in text

    # manifest 损坏 + chunks 正常(含坏 JSON 行与非对象 JSON 行,均不计入清单)
    (tmp_path / "manifest.t1.json").write_text("{bad json", encoding="utf-8")
    (tmp_path / "chunks.jsonl").write_text(
        '{"doc_name": "a.md"}\n{"doc_name": "a.md"}\nnot-json\n[1, 2]\n123\n', encoding="utf-8"
    )
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "JSONDecodeError" in text
    assert "1 篇文档" in text and "a.md(2 chunks)" in text
    assert "3 行损坏 JSON" in text

    # manifest 是合法 JSON 但缺统计字段:结构校验兜住(ValueError),不再到 KeyError
    (tmp_path / "manifest.t1.json").write_text('{"collection": "t1"}', encoding="utf-8")
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "结构非法" in text

    # manifest 与 chunks 均为非 UTF-8 字节:降级说明而非抛 UnicodeDecodeError
    (tmp_path / "manifest.t1.json").write_bytes(b"\xff\xfe{not utf8}")
    (tmp_path / "chunks.jsonl").write_bytes(b'{"doc_name": "a.md"}\n\xff\xfe\x00\xba binary')
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "UnicodeDecodeError" in text
    assert "编码损坏" in text

    # doc_name 非字符串(数组/数字):按损坏行计,不进清单、不炸 sorted
    (tmp_path / "chunks.jsonl").write_text(
        '{"doc_name": ["a.md"]}\n{"doc_name": 3}\n{"doc_name": "b.md"}\n', encoding="utf-8"
    )
    text = mcp_server._corpus_stats()
    assert "1 篇文档" in text and "b.md(1 chunks)" in text
    assert "2 行损坏 JSON" in text

    # manifest 顶层是数组:按"不可读(结构非法)"降级,不抛 TypeError
    (tmp_path / "manifest.t1.json").write_text("[]", encoding="utf-8")
    (tmp_path / "chunks.jsonl").write_text('{"doc_name": "a.md"}\n', encoding="utf-8")
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "结构非法" in text

    # 字段类型错误(collection 数组 / chunks_sha256 null 或数字):同样降级
    (tmp_path / "manifest.t1.json").write_text(
        '{"collection": [], "chunk_count": 3, "created_at": "t", "chunks_sha256": null}', encoding="utf-8"
    )
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "结构非法" in text
    (tmp_path / "manifest.t1.json").write_text(
        '{"collection": "t1", "chunk_count": 3, "created_at": "t", "chunks_sha256": 123}', encoding="utf-8"
    )
    text = mcp_server._corpus_stats()
    assert "manifest 不可读" in text and "结构非法" in text

    # 语义校验:空 collection / 负 chunk_count / sha256 不足 64 位 → 仍算不可读
    good = '{"collection": "t1", "chunk_count": 3, "created_at": "2026-01-01T00:00:00", "chunks_sha256": "%s"}'
    (tmp_path / "manifest.t1.json").write_text(good % ("a" * 64), encoding="utf-8")
    (tmp_path / "chunks.jsonl").write_text('{"doc_name": "a.md"}\n', encoding="utf-8")
    text = mcp_server._corpus_stats()
    assert "3 个 chunk" in text and "manifest 不可读" not in text  # 合法 manifest 正常展示

    for bad_m in (
        good % ("a" * 63),
        (good % ("a" * 64)).replace('"chunk_count": 3', '"chunk_count": -1'),
        (good % ("a" * 64)).replace('"t1"', '""'),
    ):
        (tmp_path / "manifest.t1.json").write_text(bad_m, encoding="utf-8")
        text = mcp_server._corpus_stats()
        assert "manifest 不可读" in text and "结构非法" in text, bad_m

    # 读取中途的 IO 故障(非编码类 OSError):降级为"读取中断",不抛错
    import builtins

    real_open = builtins.open

    def flaky_open(file, *args, **kwargs):
        fh = real_open(file, *args, **kwargs)
        return _FlakyChunksReader(fh) if str(file).endswith("chunks.jsonl") else fh

    (tmp_path / "chunks.jsonl").write_text('{"doc_name": "a.md"}\n{"doc_name": "b.md"}\n', encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", flaky_open)
        text = mcp_server._corpus_stats()
    assert "读取中断" in text and "文档清单缺席" in text


def test_corpus_stats_cache_invalidates_on_rebuild(tmp_path, monkeypatch):
    """索引重建(chunks.jsonl 被替换)后,统计随新文件更新而非沿用旧缓存。"""
    from app import mcp_server

    monkeypatch.setattr(mcp_server, "get_settings", lambda: _stub_settings(tmp_path))
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text('{"doc_name": "a.md"}\n', encoding="utf-8")
    assert "1 篇文档" in mcp_server._corpus_stats()

    # 同进程内替换语料文件:缓存 key 含 (mtime_ns, size),应失效重算
    chunks.write_text('{"doc_name": "a.md"}\n{"doc_name": "b.md"}\n', encoding="utf-8")
    assert "2 篇文档" in mcp_server._corpus_stats()


def test_search_converts_infra_exceptions(monkeypatch, caplog):
    """基础设施异常转 ToolError:客户端只见类型不见细节;可诊断错误消息完整回传。

    日志断言用 caplog(生产 stdio 进程无 handler,该 ERROR 记录会经 lastResort 落到 stderr)。
    """
    import logging

    from mcp.server.mcpserver.exceptions import ToolError

    from app import mcp_server

    class _Boom:
        def __init__(self, exc):
            self.exc = exc

        def retrieve(self, query, k):
            raise self.exc

    secret = r"C:\内部路径\model.bin"
    monkeypatch.setattr(mcp_server, "_get_retriever", lambda: _Boom(OSError(secret)))
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        with pytest.raises(ToolError) as ei:
            mcp_server._search("任意查询", 5)
    assert "检索暂不可用" in str(ei.value) and "OSError" in str(ei.value)
    assert secret not in str(ei.value)  # 内部细节不回传客户端
    assert any(r.exc_text and secret in r.exc_text for r in caplog.records)  # traceback 留服务端日志

    monkeypatch.setattr(mcp_server, "_get_retriever", lambda: _Boom(TypeError("'NoneType' object is not subscriptable")))
    with pytest.raises(ToolError) as ei:
        mcp_server._search("任意查询", 5)
    assert "检索内部错误" in str(ei.value) and "NoneType" not in str(ei.value)  # 兜底分支同样脱敏

    from pipeline.manifest import IndexValidationError

    monkeypatch.setattr(mcp_server, "_get_retriever", lambda: _Boom(IndexValidationError("索引版本校验失败:哈希不一致")))
    with pytest.raises(ToolError) as ei:
        mcp_server._search("任意查询", 5)
    assert "索引不可用" in str(ei.value) and "哈希不一致" in str(ei.value)  # 专用类型才完整回传

    # 普通 RuntimeError(依赖库也可能抛,消息可能含内部细节):不再透传,走兜底脱敏
    monkeypatch.setattr(mcp_server, "_get_retriever", lambda: _Boom(RuntimeError(r"connect http://10.0.0.1:8080 C:\secrets\llm.env")))
    with pytest.raises(ToolError) as ei:
        mcp_server._search("任意查询", 5)
    assert "检索内部错误" in str(ei.value)
    assert "secrets" not in str(ei.value) and "10.0.0.1" not in str(ei.value)
