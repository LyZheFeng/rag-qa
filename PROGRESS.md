# PROGRESS · 当前进度

> 每阶段收口更新本文件。新会话从这里接力。

## 状态：Phase 0 完成 ✅（2026-09-10）→ 下一阶段 Phase 1

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

## 下一步（Phase 1）

数据管道：loader（含占位符代码替换）→ cleaner → chunker（标题感知 512/50）→ metadata → 嵌入入 Chroma → 抽检 10 chunk → 介入点 A。

## 环境备忘

- Python 3.13.9（D:\python），venv 在 `.venv/`
- D 盘剩 ~680GB，无空间压力；HF/pip 缓存全部指向 D 盘
- Git Bash 中文坑：curl 中文乱码 → 一律 Python + UTF-8
- GitHub https 偶发重置：失败重试
