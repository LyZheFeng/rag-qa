"""Streamlit 问答界面。

启动（仓库根）：streamlit run app/ui.py
视觉:品牌青绿 + 深色侧栏,CSS 经 [data-testid] 选择器注入,选择器失效时优雅降级为默认样式。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app import __version__
from app.schemas import AskResponse

st.set_page_config(page_title="FastAPI 中文文档问答", page_icon="⚡", layout="centered")

RETRIEVER_LABELS = {
    "VectorRetriever": "纯向量(v0.1)",
    "HybridRetriever": "BM25+向量混合(v0.2)",
    "RerankRetriever": "混合+精排(v0.3)",
    "RewriteRetriever": "查询改写(v0.4)",
    "ParentChildRetriever": "父子块(v0.5)",
}
SAMPLE_QUESTIONS = [
    "如何声明请求体?",
    "Depends 依赖注入怎么用?",
    "怎么统一处理异常?",
    "后台任务 BackgroundTasks 怎么写?",
    "如何用 TestClient 做测试?",
    "路径参数如何校验和转换类型?",
]

CSS = """
<style>
:root{--acc:#009687;--acc-soft:#e6f7f4;--ink:#12332e;--muted:#64748b;--line:#e4eaee;}
html,.stApp{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;}
.stApp,[data-testid="stMarkdownContainer"]{color:var(--ink);}
.stApp{background:
 radial-gradient(1200px 420px at 50% -120px,#eaf9f6 0%,rgba(234,249,246,0) 62%),
 linear-gradient(180deg,#fbfdfd,#f5f9f8);}
[data-testid="stHeader"]{background:transparent;}
/* 本地工具用不到 deploy/分享等原生装饰,收干净 */
[data-testid="stToolbar"]{display:none;}
[data-testid="stStatusWidget"]{display:none;}
[data-testid="stMainBlockContainer"]{max-width:840px;padding-top:1.1rem;padding-bottom:5.5rem;}

.hero{text-align:center;padding:.5rem 0 .2rem;margin-bottom:.3rem;}
.hero h1{font-size:2.05rem;font-weight:800;letter-spacing:.5px;margin:0;
 background:linear-gradient(92deg,var(--acc) 12%,#2563eb 92%);-webkit-background-clip:text;background-clip:text;color:transparent;}
.hero .sub{color:var(--muted);font-size:.92rem;margin:.45rem 0 0;}
.hero .badge{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:2px;color:var(--acc);
 border:1px solid #bfe8e1;background:var(--acc-soft);border-radius:999px;padding:.18rem .85rem;margin-bottom:.55rem;}
.hero.compact h1{font-size:1.25rem;}
.hero.compact .sub{font-size:.8rem;}
.hero.compact .badge{font-size:.62rem;padding:.1rem .6rem;margin-bottom:.3rem;}

.welcome{border:1px dashed #c9d6d3;background:#ffffffcc;border-radius:14px;padding:1rem 1.2rem;margin:1rem 0 .8rem;color:#3f5753;}
.hint{color:var(--muted);font-size:.85rem;margin:.2rem 0 .55rem;}

[data-testid="stChatMessage"]{background:#fff;border:1px solid var(--line);border-radius:16px;
 box-shadow:0 1px 3px rgba(18,51,46,.05);padding:.95rem 1.15rem .8rem;margin-bottom:.95rem;}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]){background:linear-gradient(135deg,#eef9f6,#f3f8ff);border-color:#cfeae5;}
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"]{background:var(--acc)!important;}

.chip-row{margin-top:.55rem;}
.chip{display:inline-block;padding:.16rem .62rem;margin:0 .3rem .3rem 0;border-radius:999px;
 font-size:.72rem;font-weight:600;background:#eef2f5;color:#4a5b66;vertical-align:middle;}
.chip.acc{background:var(--acc-soft);color:#0b6e64;}
.chip.good{background:#e3f7e9;color:#177245;}
.chip.warn{background:#fdf1d8;color:#9a6700;}
.chip.file{font-family:Consolas,Menlo,monospace;font-size:.7rem;}

.refuse-box{border-left:4px solid #d97706;background:#fdf6e7;border-radius:8px;padding:.55rem .8rem;
 font-size:.88rem;color:#7c5a03;margin-bottom:.5rem;}

.cite-head{font-size:.82rem;font-weight:700;color:#33534d;margin:.7rem 0 .35rem;}
[data-testid="stExpander"]{border:1px solid var(--line);border-left:3px solid var(--acc);
 border-radius:10px;background:#fcfefe;margin-bottom:.45rem;}
[data-testid="stExpander"] summary{font-size:.85rem;color:#2c4440;font-weight:600;}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"]{font-size:.85rem;color:#425651;}

.stButton > button{border-radius:10px;border-color:#cfe0dc;color:#0b6e64;background:#fff;}
.stButton > button:hover{border-color:var(--acc);color:var(--acc);background:var(--acc-soft);}

[data-testid="stSidebar"]{background:linear-gradient(180deg,#0e312c 0%,#0b2226 100%);
 border-right:1px solid rgba(255,255,255,.06);}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] p{color:#cfe3df;}
[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.12);}
[data-testid="stSidebar"] .stButton > button{background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.18);
 color:#e2efec;width:100%;}
[data-testid="stSidebar"] .stButton > button:hover{background:rgba(0,150,135,.3);border-color:var(--acc);}
.side-title{font-size:.95rem;font-weight:700;color:#fff;margin:.2rem 0 .55rem;}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:.45rem;box-shadow:0 0 6px rgba(52,211,153,.55);}
.stat-row{display:flex;justify-content:space-between;gap:.8rem;padding:.34rem 0;
 border-bottom:1px dashed rgba(255,255,255,.09);font-size:.82rem;}
.stat-row .k{color:#9fc0ba;} .stat-row .v{color:#fff;font-weight:600;text-align:right;}
.side-note{font-size:.78rem;color:#8fb3ac;margin-top:.7rem;line-height:1.55;}
.side-foot{font-size:.7rem;color:#6f958d;margin-top:1rem;}
</style>
"""


@st.cache_resource(show_spinner="加载嵌入模型与检索库…")
def load_service():
    from app.service import get_service

    return get_service()


def _vector_core(service):
    """沿包装链下钻到向量检索器,取 collection/embedder 做状态展示。"""
    r = service.retriever
    while r is not None and not hasattr(r, "collection"):
        r = getattr(r, "vector", None) or getattr(r, "base", None) or getattr(r, "child", None)
    return r


def _chips_html(resp: AskResponse) -> str:
    mode_cls = {"json": "good", "retry": "warn", "fallback": "warn"}.get(resp.parse_mode, "")
    chips = [
        f'<span class="chip acc">引用 {len(resp.cited)}/{len(resp.retrieved)}</span>',
        f'<span class="chip">检索 {resp.latency.retrieve_ms}ms</span>',
        f'<span class="chip">生成 {resp.latency.generate_ms}ms</span>',
        f'<span class="chip">总计 {resp.latency.total_ms}ms</span>',
        f'<span class="chip {mode_cls}">解析 {resp.parse_mode}</span>',
    ]
    return '<div class="chip-row">' + "".join(chips) + "</div>"


def render_answer(resp: AskResponse) -> None:
    if resp.refused:
        st.markdown('<div class="refuse-box">🚫 <b>资料中缺少足够依据,已拒答</b></div>', unsafe_allow_html=True)
        st.markdown(resp.answer)
    else:
        st.markdown(resp.answer)
    st.markdown(_chips_html(resp), unsafe_allow_html=True)
    if resp.cited:
        st.markdown('<div class="cite-head">📖 引用来源 · 点击展开 chunk 原文</div>', unsafe_allow_html=True)
        for h in resp.cited:
            with st.expander(f"[{h.index}] {h.section_path} · 匹配 {h.score:.2f}"):
                st.markdown(f'<span class="chip file">{h.doc_name}</span>', unsafe_allow_html=True)
                st.markdown(h.text)


def _render_error(text: str) -> None:
    st.error(text)


def render_hero(compact: bool) -> None:
    cls = "hero compact" if compact else "hero"
    st.markdown(
        f"""<div class="{cls}">
  <div class="badge">FASTAPI · 官方中文文档 · RAG</div>
  <h1>FastAPI 中文文档问答</h1>
  <p class="sub">BM25 + 向量混合检索 top-5 → Qwen 依据资料作答 · 逐句标注引用 · 资料不足诚实拒答</p>
</div>""",
        unsafe_allow_html=True,
    )


def render_welcome() -> None:
    st.markdown(
        '<div class="welcome">👋 我是 <b>FastAPI 中文文档助手</b>。回答只基于本地入库的官方中文文档,'
        "每个说法都带来源编号,资料里没有的就直接告诉你——不编造。</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="hint">不妨从这些问题开始:</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, q in enumerate(SAMPLE_QUESTIONS):
        with cols[i % 2]:
            if st.button(q, key=f"sample_{i}", use_container_width=True):
                st.session_state.pending_question = q


def render_sidebar(service) -> None:
    core = _vector_core(service)
    name = type(service.retriever).__name__
    retriever_label = RETRIEVER_LABELS.get(name, name)
    chunks = core.collection.count() if core else "?"
    dim = getattr(getattr(core, "embedder", None), "dim", "?") if core else "?"
    rows = [
        ("检索策略", retriever_label),
        ("知识库", f"{chunks:,} chunks"),
        ("嵌入模型", f"bge-m3 · {dim} 维"),
        ("生成模型", service.generator.model),
    ]
    rows_html = "".join(f'<div class="stat-row"><span class="k">{k}</span><span class="v">{v}</span></div>' for k, v in rows)
    with st.sidebar:
        st.markdown(f'<div class="side-title"><span class="dot"></span>服务在线</div>{rows_html}', unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(
            '<div class="side-note">💡 想要<b>代码示例</b>就直接问"怎么写/怎么用";资料没覆盖的问题会收到拒答说明,'
            "换个问法或检查关键词往往就能命中。</div>",
            unsafe_allow_html=True,
        )
        if st.button("🗑 清空对话", use_container_width=True):
            st.session_state.history = []
            st.rerun()
        st.markdown(f'<div class="side-foot">rag-qa v{__version__} · 本地运行</div>', unsafe_allow_html=True)


def run_question(service, question: str) -> None:
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("检索 + 生成中…"):
            try:
                resp = service.ask(question)
            except Exception as e:
                msg = f"生成失败({type(e).__name__}):LLM 或检索服务不可用,请稍后重试。"
                _render_error(msg)
                st.session_state.history.append({"role": "assistant", "error": msg})
                return
        render_answer(resp)
    st.session_state.history.append({"role": "assistant", "resp": resp})


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if "history" not in st.session_state:
        st.session_state.history = []

    service = load_service()
    render_sidebar(service)
    render_hero(compact=bool(st.session_state.history))

    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                if "error" in msg:
                    _render_error(msg["error"])
                else:
                    render_answer(msg["resp"])
            else:
                st.markdown(msg["content"])

    if not st.session_state.history:
        render_welcome()

    if q := st.session_state.pop("pending_question", None):
        run_question(service, q)

    if question := st.chat_input("问点 FastAPI 的,例如:如何声明请求体?"):
        run_question(service, question)


main()
