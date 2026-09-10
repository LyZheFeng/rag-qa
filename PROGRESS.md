# PROGRESS · 当前进度

> 每阶段收口更新本文件。新会话从这里接力。

## 状态：Phase 0 进行中

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
- [ ] 后台：venv + 依赖安装 + bge-m3 下载（`scripts/setup_env.sh`，日志 `data/cache/setup.log`）
- [ ] 语料：clone FastAPI 中文文档 → `data/raw/fastapi-zh/`
- [ ] 验证：文档数 ≥50；bge-m3 加载成功

## 下一步（Phase 1）

数据管道：loader → cleaner → chunker（标题感知 512/50）→ metadata → 嵌入入 Chroma → 抽检 10 chunk → 介入点 A。

## 环境备忘

- Python 3.13.9（D:\python），venv 在 `.venv/`
- D 盘剩 ~680GB，无空间压力；HF/pip 缓存全部指向 D 盘
- Git Bash 中文坑：curl 中文乱码 → 一律 Python + UTF-8
- GitHub https 偶发重置：失败重试
