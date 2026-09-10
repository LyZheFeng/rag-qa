# rag-qa · RAG 知识库问答

垂直领域知识库问答系统：混合检索（向量 + BM25/RRF）→ 重排 → 查询改写，带引用溯源、拒答能力和自建评估体系（recall@5 / MRR / faithfulness / 拒答率）。

> Agent 应用开发备考 · 项目 1（对应 `agent-internship-plan.md` Week 1~2）

## 状态

🚧 开工准备中——架构与评估体系设计见交接文档。

## 技术栈

Python 3.13 · FastAPI · Chroma · bge-m3 + bge-reranker-v2-m3 · rank_bm25 · Streamlit · pydantic
