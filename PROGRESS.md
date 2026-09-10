# PROGRESS · 当前进度

> 每阶段收口更新本文件。新会话从这里接力。

## 状态：Phase 1 完成 ✅ + 介入点 A 已认可（2026-09-10）→ 下一阶段 Phase 2（基线链路）

## 已定决策

| 项 | 决定 |
|---|---|
| 语料 | FastAPI 官方中文文档（GitHub docs/zh/docs，约 150 篇 md） |
| 仓库 | 独立仓库 LyZheFeng/rag-qa（私有，终稿后转公开） |
| 生成模型 | 内网 vLLM `http://10.14.6.55:30561/v1`，`Qwen3.8-27B`，key=1234，`enable_thinking:false`，已验证可用 |
| 嵌入/重排 | 本地 bge-m3 + bge-reranker-v2-m3（HF_HOME=D 盘，hf-mirror 下载；reranker Phase 4 前再下） |
| 部署 | 学生机 Docker + frp 穿透（Phase 6，需能访问 10.14.6.55 内网） |
| 测试集配比 | 事实 100 / 推理 60 / 无法回答 40，共 200 题 |

## Phase 0 清单

- [x] 仓库初始化 + 远程推送（commit 31e243a）
- [x] WORKFLOW.md / PROGRESS.md 落盘
- [x] requirements.txt / .env.example / .env / 目录骨架
- [x] 后台：venv + 依赖安装完成（torch 2.14.0+cpu，日志 `data/cache/setup.log`）
- [x] 语料：`data/raw/fastapi-zh/` 124 篇 md（943KB）+ `data/raw/fastapi-docs-src/` 461 个代码文件（752KB）
- [x] 验证：bge-m3 离线加载成功，1024 维，单条编码含加载 2.4s（缓存 `data/cache/hf/`，使用时设 `HF_HOME=D:\LLM_training\rag-qa\data\cache\hf`）

## 语料关键发现（Phase 1 loader 的输入约束）

- 正文代码是占位符 `{* ../../docs_src/xxx.py hl[n] *}`，需在 loader 替换为真实代码块（440 处，仅 1 处指向 docs_src 外的源码，保留文字引用）
- 标题带自定义锚点（`## 标题 { #anchor }`），清洗时剥离锚点、保留标题文本与层级
- `/// warning | 警告 ... ///` 告示块转为普通文本标记（如"⚠️ 警告:"）

## Phase 1 清单（数据管道）

- [x] `pipeline/`：models / cleaner / loader / chunker / config / embed / store，15 个单测全过（`tests/test_pipeline.py`）
- [x] 清洗：frontmatter、占位符 440 处全处理（439 解析为真实代码块 + 1 处外部源码保留文字引用）、`{! !}` include 6 处、标题锚点剥离、告示块/选项卡转文本标记、行内 HTML 剥离、base64 超长行截断
- [x] 切块基线：标题感知 512/50，**不变量 chunk.text == full_text[char_span] 全库 1701/1701 通过**
- [x] 嵌入入 Chroma：bge-m3（CPU，391s），`data/chroma/` collection `fastapi_zh_v1`，确定性 id + 按文档先删后加，重跑幂等
- [x] 产物：**122 篇 → 1701 chunk**（字符中位 298 / token 中位 137，最大 348，无截断风险），`data/chunks/chunks.jsonl`
- [x] 介入点 A 材料：`data/chunks/samples.md`（10 条抽检，含上下文与 span 回切验证）、`data/chunks/stats.md`（分布统计）
- [x] 检索冒烟：3 个手工问题全部命中正确章节（cos 距离 0.18~0.34）

## 语料关键发现（Phase 1 补充）

- 占位符语法比 Phase 0 记录更丰富：多区间行号 `ln[1:9,29:35]`、`hl[23:26]`、`title["..."]`（17 处）
- `{!> path !}` / `{! path !}` include 语法（6 处，在代码围栏内嵌入文件原文）
- `stream-data.md` 有 base64 图片字面量（单行 4000+ 字符），已按 1000+ 字符行截断
- 排除非正式文档：`_llm-test.md`（翻译 QA 测试页）、`translation-banner.md`（局部片段），124 → 122 篇

## 下一步

**Phase 2 基线链路**：向量 top-5 检索 → 编号上下文 → Qwen3.8-27B 生成（pydantic：answer/citations/refused，解析失败重试 1 次降级纯文本）→ FastAPI `POST /ask` → Streamlit 界面。验证：5 个手工问题端到端 + 延迟。完成后 tag `v0.1-baseline`，介入点 B 演示。

Phase 2 可直接复用：
- 检索：`pipeline/embed.py` 的 `encode_queries()` + Chroma collection `fastapi_zh_v1`（`data/chroma/`）
- 冒烟已验证检索质量：3 问全部命中正确章节（cos 距离 0.18~0.34）
- 生成走 `.env` 的 LLM_BASE_URL/LLM_MODEL（`enable_thinking:false`），注意 Git Bash 中文坑：请求一律 Python + UTF-8

## 环境备忘

- Python 3.13.9（D:\python），venv 在 `.venv/`
- D 盘剩 ~680GB，无空间压力；HF/pip 缓存全部指向 D 盘
- Git Bash 中文坑：curl 中文乱码 → 一律 Python + UTF-8
- GitHub https 偶发重置：失败重试
