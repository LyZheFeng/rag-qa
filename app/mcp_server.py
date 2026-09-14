"""rag-qa 文档检索 MCP server(项目 4 Day 24)。

把 `app/retriever.get_retriever()` 的混合检索栈(向量 + BM25 + RRF,模式由 .env
的 RETRIEVER 决定,默认 hybrid)原样暴露为 MCP 三类原语,检索逻辑零改动——
与 chatbi 的数据库查询 server 同一设计原则:MCP 是工具的传输协议,不改工具的语义;
RAG 生成(编号上下文、引用、拒答纪律)留在客户端。

- tools(模型按参数调用):`search(query, top_k)` → 编号 chunk 列表,
  编号口径与 `generator.build_context` 一致([N] 来源:文档 > 小节),客户端可直接沿用引用纪律;
- resources(客户端按址读取):`rag-qa://corpus` 索引与语料统计(manifest 同源);
- prompts(用户主动触发):`answer_with_citations` 把"忠于检索内容、编号引用、
  不足即拒答"的 RAG 纪律封装成模板。

运行(stdio transport):`python -m app.mcp_server`。启动只读配置(秒级),
嵌入模型/索引在首次 search 时才加载(~3s,进程内只付一次)——Inspector 里
tools/list 立即可见,不用等模型。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from pipeline.config import get_settings

_TOP_K = Field(default=5, ge=1, le=10, description="返回的 chunk 条数(1~10)")
_QUERY = Field(min_length=2, max_length=1000, description="自然语言检索 query")


def _get_retriever():
    """懒加载单例:首次 search 才加载嵌入模型与索引(get_retriever 自带 lru_cache)。"""
    from app.retriever import get_retriever

    return get_retriever()


def _format_hits(hits) -> str:
    """把检索命中压成模型友好的编号文本,与 generator.build_context 的编号口径一致。"""
    mode = get_settings().retriever
    head = f"共 {len(hits)} 条(检索模式 {mode})"
    blocks = [
        f"[{h.index}] 来源:{h.doc_name} > {h.section_path}(score {h.score})\n{h.text}"
        for h in hits
    ]
    return head + ("\n\n" + "\n\n".join(blocks) if blocks else "\n(无命中:query 与语料不相关,或可换一种问法重试)")


@lru_cache(maxsize=1)
def _corpus_stats() -> str:
    """索引 manifest + 语料文档清单(chunks.jsonl 读一次缓存)。"""
    import json

    s = get_settings()
    from pipeline.manifest import manifest_path

    parts = [f"检索模式:{s.retriever}(向量 {s.embed_model} + BM25,bge-m3 1024 维)"]
    m_path = manifest_path(s.chroma_dir, s.collection)
    if m_path.exists():
        m = json.loads(m_path.read_text(encoding="utf-8"))
        parts.append(
            f"索引:{m['collection']},{m['chunk_count']} 个 chunk,构建于 {m['created_at']}"
            f"(chunks sha256 前 12 位 {m['chunks_sha256'][:12]})"
        )
    docs: dict[str, int] = {}
    with open(s.chunks_path, encoding="utf-8") as f:
        for line in f:
            name = json.loads(line).get("doc_name")
            if name:
                docs[name] = docs.get(name, 0) + 1
    parts.append(f"语料:{len(docs)} 篇文档(FastAPI 官方中文文档)")
    listing = "\n".join(f"- {name}({n} chunks)" for name, n in sorted(docs.items()))
    return "\n".join(parts) + "\n\n文档清单:\n" + listing


def _build_server():
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer(
        name="rag-qa-docs",
        instructions=(
            "FastAPI 中文文档的混合检索 server。用 search 按语义/关键词找 chunk,"
            "返回带编号的原文片段;回答时忠于检索内容并按编号引用,资料不足应拒答。"
        ),
    )

    @server.tool(name="search", description=(
        "在 FastAPI 中文文档语料(122 篇,1701 个 chunk)中做混合检索"
        "(向量 + BM25 + RRF 融合),返回编号的原文片段(含来源文档、小节路径、得分)。"
        "回答文档问题前应先检索;编号可直接用作引用标注。"
    ))
    def search(query: str = _QUERY, top_k: int = _TOP_K) -> str:
        """query:自然语言问题或关键词;top_k:返回条数(默认 5,最多 10)。"""
        try:
            hits = _get_retriever().retrieve(query, k=top_k)
        except RuntimeError as e:
            # manifest 校验失败(索引与配置错配)是"预期内可诊断"的错误,消息完整回传
            raise ToolError(f"索引不可用:{e}") from e
        return _format_hits(hits)

    @server.resource(
        "rag-qa://corpus", name="corpus", description="语料与索引统计:检索模式、chunk 数、122 篇文档清单",
    )
    def corpus_resource() -> str:
        return _corpus_stats()

    @server.prompt(name="answer_with_citations", description="RAG 回答纪律模板:忠于检索内容、编号引用、不足即拒答")
    def answer_with_citations(question: str) -> str:
        return f"""请依据检索到的编号资料回答问题:{question}

规则(与 rag-qa 主链路同一套纪律):
1. 先用 search 检索(问题不清时可换关键词再检索一次);只依据资料回答,答案中在对应句子末尾标注资料编号,如 [1] 或 [2][3];代码示例直接保留资料中的代码;
2. 资料不足以回答问题时必须拒答:明确说明缺少什么信息,禁止编造;不要用训练记忆补充语料里没有的 API 行为;
3. 回答末尾列出实际用到的来源(文档名 > 小节路径)。"""

    return server


mcp = _build_server()


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
