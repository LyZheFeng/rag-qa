# PROGRESS · 当前进度

> 每阶段收口更新本文件。新会话从这里接力。

## 状态：Phase 3 完成 ✅ + Phase 4 v0.2 完成 ✅（tag `v0.2-hybrid`，2026-09-10）→ 明日 v0.3-rerank（代码已就绪）

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

## Phase 2 清单（基线链路）

- [x] `app/` 包：schemas（pydantic 契约）/ retriever（bge-m3 + Chroma top-k）/ generator / service（编排+延迟）/ api（FastAPI）/ ui（Streamlit chat）
- [x] 生成契约：`{answer, citations, refused}` 严格 JSON；剥围栏/`</think>` 后取首 `{` 末 `}`；解析失败重试 1 次（带纠正提示），再失败降级纯文本；`parse_mode` 记录 json/retry/fallback
- [x] 引用与拒答：citations 在 pydantic **之前**于原始 dict 上清洗（去越界/去重/排序，refused 强制清空）；服务层富化为完整 chunk 信息（cited 字段）
- [x] FastAPI：`POST /ask`（k 可调 1~10）、`GET /health`，lifespan 预热嵌入模型（首问检索不付加载耗时），LLM 断连统一 502
- [x] Streamlit：chat 界面 + 引用卡片展开 chunk 原文 + 相似度/延迟/parse_mode 标注，`st.cache_resource` 单例
- [x] 单测 16 个新增（全库 31 过，全部无网络；AppTest 验证 UI 可跑）
- [x] 冒烟 `scripts/smoke_phase2.py`：5 问端到端，检索均值 90ms / 生成均值 1.8s / 端到端均值 1.9s（最大 3.1s）；4 题正常引用作答 + 1 题正确拒答（gRPC，语料确无）
- [x] FastAPI 实测：中文 POST 正常，`uvicorn app.api:app --port 8010` → health/ask 全通
- [x] tag `v0.1-baseline`

## Phase 2 关键发现（Phase 4 的输入）

- 介入点 B 复测(2026-09-10):"Depends 怎么用?"当日未复现误拒(答上且 2 条引用)——该弱项按"偶发"处理,v0.2-hybrid 落地后用测试集回归验证,不依赖单次手工复现

- **Depends 用法误拒**：问"Depends 怎么用"，top-5 全是概念/小结 chunk（0.71~0.76），真正的代码示例 chunk 未入围，模型如实拒答（无编造）。→ 纯向量对"要代码示例"类问题弱，v0.2-hybrid（BM25 代码词精确匹配）的直接动机
- 拒答答案质量好：会说明"资料里只有概念没有用法"，不是干巴巴一句"不知道"
- 生成延迟 0.9~2.9s/问（temperature=0），检索稳定在 50~200ms（预热后）
- pydantic v2 `list[int]` 会把 JSON `true` 强转成 `1`：LLM JSON 必须先在原始 dict 上清洗再进模型（见 pitfalls）

## Phase 3 清单(评估体系,进行中)

- [x] `eval/` 模块:question_gen / sampling / screen / judge / metrics / run_eval / export_review,单测 9 个新增(全库 40 过)
- [x] 出题:240 题(事实 120/推理 72/无法回答 48),零失败零重复,分层抽样覆盖 116 文档;出题 temp 0.7/0.9(数据构造允许,评估跑批严格 0)
- [x] 预筛:gold 一致性复核 + 无法回答题检索复核(红线 2),剔除 gold_mismatch 11 / corpus_answers 3 → 入选 200 题(100/60/40),覆盖 100 文档,单文档同类型 ≤3;记录留档 `data/eval/screening_report.jsonl`
- [x] 审核文件导出:`data/eval/review_questions.md`(200 题,介入点 C 待用户确认)
- [x] 介入点 C:用户确认通过(2026-09-10,200 题无删改)
- [x] v0.1-baseline 全量评估 → results.md 基线行(正确性 3.92 / 误拒 18.1% / 拒答正确 97.5%)
- [x] v0.2-hybrid 全量评估 → results.md 追加行 + tag(正确性 4.41 / 误拒 7.5% / 拒答正确 100%)

## Phase 4 清单(优化循环)

- [x] v0.2-hybrid:内置 BM25(中文 bigram+ASCII 词)+ RRF 融合,RETRIEVER 开关;Depends 弱项修复(top-3 全是代码示例 chunk)
- [x] v0.3-rerank 代码预备:CrossEncoder 精排器(bge-reranker-v2-m3 已下载验证,CPU 加载 4min/打分 0.14s),RETRIEVER=rerank 启用,**待跑**:检索层验证 → 快评 → 全量
- [ ] v0.4-rewrite 多查询扩展
- [ ] v0.5-chunking 对比(固定/标题语义/父子)
- [ ] 30 条人机一致性抽样(需用户参与,记录已够)

### Phase 3 关键发现

- **v0.2-hybrid 检索层验证(全量 160 可答题,无 LLM)**:chunk recall@5 64.4%→83.1%(+18.8pp)、MRR 52.3%→65.6%、doc 口径 87.5%→94.4%;recall@10 chunk 达 93.1% → v0.3-rerank(粗20精5)的候选池足够
- rank-bm25 0.2.2 + NumPy 2.x 静默全 0 分 → 自实现 Okapi BM25(见 pitfalls)

- **50 题冒烟(v0.1-baseline-smoke,非正式数字)**:事实题 RAG 4.44 vs 无检索 3.76(RAG 增益明确);推理题 RAG 3.21 vs 无检索 4.36(检索反而拖累);faithfulness 0.985;无法答题 10/10 正确拒答;误拒 15%(6/40)
- **doc 口径 recall 97.5% vs chunk 口径 67.5%**:几乎总能找到对的文档,但 top-5 里没有承载答案的那个 chunk——误拒的低分案例全部是 gold 不在 top5,模型看到"邻而不准"的 chunk 后诚实拒答。→ 系统不答是"检索没送到"而非"模型不会",v0.2-hybrid/v0.3-rerank/父子 chunk 的直接依据
- 推理题是"为什么"类,chunk 被拒后模型保守按资料拒答,而裸模型凭参数知识能答——说明推理题对检索精度更敏感

- 出题时"为什么"类推理题易超出 chunk 支撑范围(资料只讲是什么不讲原理),gold 一致性复核是必要闸门(11/240 命中)
- 无法回答题生成会撞上语料实有内容(PyJWT、SQLAlchemy session),检索复核 3/48 命中,证实红线 2 不能省
- 评估链路:每题 5 次 LLM 调用(RAG 生成 + 无检索对照 + 3 项 judge),全量 200 题 ≈ 35~40 分钟

## 下一步

**明日 v0.3-rerank**(代码已就绪,改 .env `RETRIEVER=rerank` 即跑):检索层验证(约 10min)→ 50 题快评(13min)→ 全量(40min)→ results.md + tag。
之后 v0.4-rewrite → v0.5-chunking → Phase 5 拒答校准(v0.2 误拒 7.5% 已达 ≤10% 目标,重点保持)→ Phase 6 部署(介入点 D)。
另有 30 条人机一致性抽样待用户抽空参与。

### 今日评估链路备忘

- 全量 200 题 ≈ 40 分钟(每题 5 次 LLM 调用);快评 50 ≈ 12 分钟
- 无检索对照列同题复跑完全一致(3.86),judge 复现性良好
- eval/runs/ 已留档 3 个 run(v0.1-smoke/v0.1-full/v0.2-full)

## 环境备忘

- Python 3.13.9（D:\python），venv 在 `.venv/`
- D 盘剩 ~680GB，无空间压力；HF/pip 缓存全部指向 D 盘
- Git Bash 中文坑：curl 中文乱码 → 一律 Python + UTF-8
- GitHub https 偶发重置：失败重试
