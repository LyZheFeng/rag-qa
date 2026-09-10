"""Streamlit 问答界面（介入点 B 演示入口）。

启动（仓库根）：streamlit run app/ui.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from app.schemas import AskResponse

st.set_page_config(page_title="FastAPI 中文文档问答", page_icon="📚", layout="centered")


@st.cache_resource(show_spinner="加载嵌入模型与检索库…")
def load_service():
    from app.service import get_service

    return get_service()


def render_answer(resp: AskResponse) -> None:
    if resp.refused:
        st.warning("🚫 无法从文档中回答：" + resp.answer, icon="🚫")
    else:
        st.markdown(resp.answer)
    if resp.cited:
        st.caption(f"引用 {len(resp.cited)} 条 · 检索 {len(resp.retrieved)} 条 · "
                   f"检索 {resp.latency.retrieve_ms}ms + 生成 {resp.latency.generate_ms}ms "
                   f"= {resp.latency.total_ms}ms · 解析 {resp.parse_mode}")
        for h in resp.cited:
            with st.expander(f"[{h.index}] {h.doc_name} · {h.section_path}（相似度 {h.score:.3f}）"):
                st.markdown(h.text)
    else:
        st.caption(f"无引用 · 检索 {len(resp.retrieved)} 条 · {resp.latency.total_ms}ms · 解析 {resp.parse_mode}")


def main() -> None:
    st.title("📚 FastAPI 中文文档问答")
    st.caption("基线链路 v0.1：bge-m3 向量 top-5 检索 → Qwen 生成（带引用/拒答）· 语料 122 篇官方中文文档")

    if "history" not in st.session_state:
        st.session_state.history = []

    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                render_answer(msg["resp"])
            else:
                st.markdown(msg["content"])

    if question := st.chat_input("问点 FastAPI 的，例如：如何声明请求体？"):
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        service = load_service()
        with st.chat_message("assistant"):
            with st.spinner("检索 + 生成中…"):
                try:
                    resp = service.ask(question)
                except Exception as e:
                    st.error(f"生成失败：{type(e).__name__}: {e}")
                    return
            render_answer(resp)
        st.session_state.history.append({"role": "assistant", "resp": resp})


main()
