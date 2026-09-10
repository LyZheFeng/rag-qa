# rag-qa 工作流程（跨会话执行依据）

> 新会话开工：读本文件 + `PROGRESS.md` + 仓库根上级的 `agent-internship-plan.md` / `project1-kickoff.md` 即可接力。

## 全局约定

- 进度落盘：每阶段收口更新 `PROGRESS.md`；踩坑笔记追加到 `notes/pitfalls.md`（问题 → 尝试 → 结论，3 行）
- 小步提交，commit message 写"为什么"；每版本打 tag
- 全程 UTF-8：中文请求走 Python（`sys.stdout.reconfigure(encoding='utf-8')`），不用 Git Bash curl 发中文
- 评估纪律：temperature=0；迭代用 `--limit 50` 子集；**进 README 的数字必须全量真实跑出**，脚本与原始输出留档于 `eval/runs/`
- 模型环境：生成走内网 vLLM（见 `.env`）；嵌入/重排本地 bge（HF_HOME=D 盘缓存，HF_ENDPOINT=hf-mirror）
- 用户介入点：A 认可 chunk 样例 → B 体验基线演示 → C 审 200 题测试集 → D 提供学生机/frp 信息

## 阶段

### Phase 0 · 开工准备
venv + 依赖 + bge-m3 下载；clone FastAPI 中文文档语料；目录骨架；`.env`。
验证：文档数量、bge-m3 可加载。产出：可运行空骨架。

### Phase 1 · 数据管道
md loader → 统一中间格式（正文+标题链+段落号）→ 清洗 → chunker（策略接口，基线=标题感知 512/50）→ metadata（chunk_id/doc_name/section_path/char_span/hash）→ bge-m3 嵌入 → Chroma（hash 幂等去重）。
验证：抽 10 chunk 对照原文；统计 token 分布。**介入点 A**。产出：`data/chroma/` + 管道 CLI。

### Phase 2 · 基线链路
向量 top-5 → 编号上下文 → 生成（pydantic：answer/citations/refused，解析失败重试 1 次降级纯文本）→ FastAPI `POST /ask` → Streamlit。
验证：5 个手工问题端到端 + 延迟。**介入点 B**。tag `v0.1-baseline`。

### Phase 3 · 评估体系
分层抽 chunk → Qwen3.8-27B 生成 200 题（事实 100/推理 60/无法回答 40，带标准答案+gold chunk_id）→ 我预筛（含检索复核"无法回答"）→ 导出审核文件给用户（**介入点 C**，可异步）。
评估脚本：recall@5（chunk/doc 双口径）、MRR、faithfulness（judge 拆 claim）、正确性（1~5 分 + 30 条人机一致性）、拒答率（分开统计）+ 无检索对照列。基线数字进 `eval/results.md`。与 Phase 4 并行推进。

### Phase 4 · 优化循环
每轮固定节奏：实现 → 50 题快评 → 调参 → 全量评估 → results.md 追加行 → git tag → 踩坑笔记。
v0.2-hybrid（BM25 中文 bigram + RRF）→ v0.3-rerank（粗 20 精排 5）→ v0.4-rewrite（多查询扩展）→ v0.5-chunking（固定/标题语义/父子对比选优）。

### Phase 5 · 溯源与拒答完善
引用卡片展开原文；拒答阈值校准（无法回答型正确拒答 ≥90%、可答题误拒 ≤10%），校准曲线留档。

### Phase 6 · 部署 + 文档
Docker 化（**介入点 D**：学生机+frp）→ 公网链接 → README 终稿（架构图/评估表/运行说明/踩坑 Top 3）→ 公网验收。

## 红线

1. 评估数字必须真实跑出，禁止编造/脑补
2. 测试集"无法回答型"必须人工确认语料无答案，拒答率单独统计
3. 语料相对 LLM 训练分布偏热门，必须保留"无检索直接问"对照列证增益
