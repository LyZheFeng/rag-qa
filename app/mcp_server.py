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

安全边界:仅面向本地 stdio(继承本机用户权限,无认证/授权)。改挂 SSE /
Streamable HTTP 前,search 与 corpus 会直接暴露在网络上,必须先补认证、
访问控制、限流与审计。
"""

from __future__ import annotations

import logging

from pydantic import Field

from pipeline.config import get_settings

# 沿用 retriever.py 的服务端错误通道;stdio 进程无 uvicorn handler,落到 stderr 兜底
logger = logging.getLogger("uvicorn.error")

_TOP_K = Field(default=5, ge=1, le=10, description="返回的 chunk 条数(1~10)")
_QUERY = Field(min_length=2, max_length=1000, description="自然语言检索 query")


def _get_retriever():
    """懒加载单例:首次 search 才加载嵌入模型与索引(get_retriever 自带 lru_cache)。"""
    from app.retriever import get_retriever

    return get_retriever()


def _search(query: str, top_k: int) -> str:
    """检索 + 异常边界(模块级,便于单测)。

    IndexValidationError = manifest 校验失败的专用类型,消息为面向用户的
    诊断(哪个文件、什么不一致、怎么修),完整回传;其余异常分两类脱敏——
    OSError/ValueError 等基础设施异常回"检索暂不可用",任何其他异常(含依赖
    库抛出的普通 RuntimeError,其消息可能含内部路径/配置/地址)兜底回"检索
    内部错误"。脱敏两类只回传异常类型,完整 traceback 留服务端日志。
    注意:ToolError 继承自 Exception——本函数把 ToolError 的抛出全部放在
    except 分支里、try 内只有 retrieve() 调用,结构上不会被兜底分支吞掉;
    改动时保持这一不变量。
    """
    from mcp.server.mcpserver.exceptions import ToolError
    from pipeline.manifest import IndexValidationError

    try:
        hits = _get_retriever().retrieve(query, k=top_k)
    except IndexValidationError as e:
        raise ToolError(f"索引不可用:{e}") from e
    except (OSError, ValueError) as e:
        logger.error("search 基础设施异常(query=%r)", query, exc_info=e)
        raise ToolError(f"检索暂不可用({type(e).__name__}),详情见 server 端日志") from e
    except Exception as e:
        logger.error("search 未预期异常(query=%r)", query, exc_info=e)
        raise ToolError(f"检索内部错误({type(e).__name__}),详情见 server 端日志") from e
    return _format_hits(hits)


def _format_hits(hits) -> str:
    """把检索命中压成模型友好的编号文本,与 generator.build_context 的编号口径一致。"""
    mode = get_settings().retriever
    head = f"共 {len(hits)} 条(检索模式 {mode})"
    blocks = [
        f"[{h.index}] 来源:{h.doc_name} > {h.section_path}(score {h.score})\n{h.text}"
        for h in hits
    ]
    return head + ("\n\n" + "\n\n".join(blocks) if blocks else "\n(无命中:query 与语料不相关,或可换一种问法重试)")


def _file_state(path) -> tuple[int, int] | None:
    """(mtime_ns, size) 作为缓存失效依据;文件不存在返回 None。"""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _manifest_shape_ok(m) -> bool:
    """统计展示所需的 manifest 结构/语义校验。

    顶层为对象;collection/created_at 为非空字符串;chunk_count 为非负整数
    (排除 bool);chunks_sha256 为长度 64 的字符串。类型外的语义问题(空串、
    负数、截断的哈希)会让统计失真,一并拒绝。
    """
    if not isinstance(m, dict):
        return False
    col = m.get("collection")
    count = m.get("chunk_count")
    created = m.get("created_at")
    sha = m.get("chunks_sha256")
    return (
        isinstance(col, str) and col != ""
        and isinstance(count, int) and not isinstance(count, bool) and count >= 0
        and isinstance(created, str) and created != ""
        and isinstance(sha, str) and len(sha) == 64
    )


_corpus_cache: tuple[tuple, str] | None = None


def _corpus_stats() -> str:
    """索引 manifest + 语料文档清单(展示性统计,降级不抛错)。

    manifest 缺失/损坏/编码错误/结构非法、chunks 不可读/编码损坏、行内 JSON
    或 doc_name 非法(非对象、非字符串)时,把原因写进返回文本而不是抛裸
    异常——resource 读的是统计,真正的版本校验在 retriever 启动路径上
    (由 search 的 ToolError 承担)。按文件 (mtime, size) 缓存:索引重建
    替换文件后自动失效。
    """
    global _corpus_cache
    import json

    s = get_settings()
    from pipeline.manifest import manifest_path

    m_path = manifest_path(s.chroma_dir, s.collection)
    key = (
        s.retriever,
        s.embed_model,
        str(m_path),
        _file_state(m_path),
        str(s.chunks_path),
        _file_state(s.chunks_path),
    )
    if _corpus_cache is not None and _corpus_cache[0] == key:
        return _corpus_cache[1]

    parts = [f"检索模式:{s.retriever}(向量 {s.embed_model} + BM25,bge-m3 1024 维)"]
    if m_path.exists():
        try:
            m = json.loads(m_path.read_text(encoding="utf-8"))
            if not _manifest_shape_ok(m):
                # 顶层不是对象 / 字段类型不对(如 chunks_sha256=null、collection=[]),
                # 或语义非法(空串、负数、哈希长度不足),统一按"不可读"降级
                raise ValueError(
                    "结构非法:顶层应为对象,且 collection/created_at 为非空字符串、"
                    "chunk_count 为非负整数、chunks_sha256 为 64 位字符串"
                )
            parts.append(
                f"索引:{m['collection']},{m['chunk_count']} 个 chunk,构建于 {m['created_at']}"
                f"(chunks sha256 前 12 位 {m['chunks_sha256'][:12]})"
            )
        except (OSError, ValueError, KeyError) as e:  # ValueError 含 UnicodeDecodeError/JSONDecodeError
            parts.append(
                f"索引:manifest 不可读({type(e).__name__}: {e}),统计缺席;检索可用性以 search 的报错为准"
            )
    else:
        parts.append(f"索引:manifest 不存在({m_path}),旧索引建议重跑 build_index 生成")

    docs: dict[str, int] = {}
    bad_lines = 0
    try:
        f = open(s.chunks_path, encoding="utf-8")
    except OSError as e:
        # 不缓存:下次读取重试,文件恢复后统计自动回来
        return "\n".join(parts) + f"\n语料:chunks 文件不可读({e}),文档清单缺席"
    try:
        with f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                if not isinstance(record, dict):
                    # 合法 JSON 但不是对象(数组/字符串/数字/字面量):同样按损坏行计
                    bad_lines += 1
                    continue
                name = record.get("doc_name")
                if isinstance(name, str) and name:
                    docs[name] = docs.get(name, 0) + 1
                elif name is not None:
                    # doc_name 存在但不是非空字符串(数组/数字/…):防 unhashable
                    # 与 sorted 混型比较错误,按损坏行计
                    bad_lines += 1
    except UnicodeDecodeError:
        return "\n".join(parts) + "\n语料:chunks 文件编码损坏(非 UTF-8),文档清单缺席"
    except OSError as e:
        # 读取中途的 IO 故障(磁盘错误、文件被截断等):同样降级;不缓存,恢复后重试
        return "\n".join(parts) + f"\n语料:chunks 读取中断({e}),文档清单缺席"
    parts.append(f"语料:{len(docs)} 篇文档(FastAPI 官方中文文档)")
    if bad_lines:
        parts.append(f"(另有 {bad_lines} 行损坏 JSON 或非法 doc_name,未计入清单)")
    listing = "\n".join(f"- {name}({n} chunks)" for name, n in sorted(docs.items()))
    text = "\n".join(parts) + "\n\n文档清单:\n" + listing
    _corpus_cache = (key, text)
    return text


def _build_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="rag-qa-docs",
        instructions=(
            "FastAPI 中文文档的混合检索 server。用 search 按语义/关键词找 chunk,"
            "返回带编号的原文片段;回答时忠于检索内容并按编号引用,资料不足应拒答。"
        ),
    )

    @server.tool(name="search", description=(
        "在 FastAPI 中文文档语料中做混合检索(向量 + BM25 + RRF 融合),"
        "返回编号的原文片段(含来源文档、小节路径、得分)。"
        "回答文档问题前应先检索;编号可直接用作引用标注;"
        "当前 chunk 数与文档清单以 rag-qa://corpus 资源为准(随索引重建更新)。"
    ))
    def search(query: str = _QUERY, top_k: int = _TOP_K) -> str:
        """query:自然语言问题或关键词;top_k:返回条数(默认 5,最多 10)。"""
        return _search(query, top_k)

    @server.resource(
        "rag-qa://corpus", name="corpus", description="语料与索引统计:检索模式、chunk 数、文档清单(manifest 同源)",
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
