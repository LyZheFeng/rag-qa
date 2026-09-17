# rag-qa 前端(Next.js)

FastAPI 中文文档问答的正式前端：SSE 流式渲染 + 引用溯源交互。替代 Streamlit 版(`app/ui.py`)。

## 本地开发

```bash
# 1) 起后端(仓库根,首次会加载嵌入模型,耐心等就绪日志)
uvicorn app.api:app --port 8000

# 2) 起前端
cd web
npm install
npm run dev        # http://localhost:3000
```

后端地址用 `NEXT_PUBLIC_API_BASE` 覆盖(见 `.env.local`);跨域来源在后端 `.env` 的 `CORS_ORIGINS` 配置。

## 结构

- `app/page.tsx` — 对话页状态机(retrieving → streaming → done/error),消费 `/ask/stream`
- `components/AssistantMessage.tsx` — 单条助手消息:流式光标、拒答盒、指标 chips、引用展开卡片
- `components/Markdown.tsx` + `lib/rehype-citations.ts` — Markdown 渲染与 `[n]` 角标可点击化
- `components/Sidebar.tsx` — `/health` 轮询、服务状态、清空对话
- `lib/types.ts` — 与后端 `app/schemas.py` 逐字段对齐的 TS 契约
- `lib/sse.ts` — fetch + ReadableStream 的 SSE 解析(EventSource 不支持的场景)

## SSE 事件协议(与后端 `app/api.py` 对齐)

```
event: sources  → {"hits": Hit[]}            检索完成,前端亮出"已检索 N 条"
event: delta    → {"text": "..."}            临时增量文本,追加显示
event: retry    → {"message": "..."}         首次解析失败,前端清空临时文本重打
event: done     → AskResponse                权威终态,前端以此覆盖显示
event: error    → {"message", "trace_id"}    错误收尾
```
