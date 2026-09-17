# PROGRESS · 当前进度

> 每阶段收口更新本文件。新会话从这里接力。

## 状态:阶段五 · 前端工作流全部完成(2026-09-17,Streamlit 已移除,Next.js 为唯一前端;详细见「阶段五」节)→ 主线收口

## 阶段五 · 统一与收尾完成情况(2026-09-17,`frontend-upgrade-workflow.md` 阶段 5;chatbi 侧改动见其仓 PROGRESS)

- **前端统一(复制对齐)**:`web/lib/sse.ts` 与 chatbi 逐字对齐(补 headers 参数,本仓调用点兼容);版心 840→860px;`next.config.ts` 补 `allowedDevOrigins: ["127.0.0.1"]`——**本仓实测踩坑:用 127.0.0.1 访问 dev server 时 Next 默认拦截跨源 HMR/chunk,页面停在未水合状态(按钮无响应、轮询不走),之前会话都用 localhost 访问未暴露**;`npm run build` 含 TS 检查通过
- **移除 Streamlit**:`app/ui.py` 删除(历史见 git);requirements.txt 去 streamlit(本仓无 lock,重装验证以「卸载 streamlit → 94 例全绿」执行:业务代码零 streamlit 传递依赖引用,ui.py 仅 stdlib+streamlit+app 模块);`app/api.py` sys.path 注释、Dockerfile `EXPOSE 8000 8501 → 8000`、README 运行说明同步
- **README**:快速开始改 uvicorn + `web/` 前端;新增「界面」节配 `docs/web-ui.png`(本次重拍:流式回答 + `[n]` 角标展开 chunk 原文 + 拒答盒同框)
- **验收(= 计划通关标准③)**:浏览器实测——两轮对话分别走拒答路径(拒答盒 + 引用 0/5)与正常引用路径(流式打字机 + `[1]` 角标点击展开 chunk 原文 + 引用来源卡),侧栏服务在线;无 Streamlit 痕迹
- **环境观察(非回归)**:「Depends 依赖注入怎么用?」在当前 vLLM 服务端状态下被生成侧拒答(检索正常,首命中 tutorial/dependencies/index.md score 0.977;另两道原通过题仍正常出引用)——temperature=0 的确定性只在不重启的同一服务端内成立,跨会话的共享 vLLM 状态漂移会改变单题表现,评估数字以当次跑批为准

## 阶段四 · rag-qa 前端改造完成情况(2026-09-17)

- **后端只加接口**(零回归,全量 94 例测试绿,新增 13 例 `tests/test_stream_api.py`):
  - `GET /ask/stream`(SSE):事件序 `sources`(检索完成推全部命中)→ `delta*`(临时增量)→ [`retry` → `delta*`]* → `done`(权威终态,完整 AskResponse);错误收拢为 `error` 事件(含 trace_id,与 /ask 502 同口径);并发沿用 `_ask_semaphore`(拿放都在同步生成器内,流结束即释放,有测试)
  - **严格 JSON 契约与流式并存的解法**:LLM 仍输出单 JSON,服务端 `scan_answer()` 从半成品 JSON 增量解出 answer 字段前缀下发(容忍 `</think>` 前缀、嵌套/字符串内出现的伪 "answer" 键、尾部不完整转义 `\`/`\uXXX`);流中显示是临时的,`retry` 事件让前端清空重打,权威状态永远是完整解析后的 done——解析纪律未放松
  - CORS:Settings 新增 `cors_origins`(逗号分隔,默认 localhost:3000 两写法);`iterate_in_threadpool` 桥接同步生成器,不占事件循环
- **前端 `web/`**(Next.js 16.3 + React 19.2 + Tailwind v4,`npm run build` 含 TS 检查通过):
  - 结构见 `web/README.md`;`lib/types.ts` 与 `app/schemas.py` 逐字段对齐;`lib/sse.ts` 用 fetch+ReadableStream 解析 SSE(EventSource 不支持自定义头);`lib/rehype-citations.ts` 把答案内 `[n]` 替换为可点击角标(自写 rehype 插件遍历文本节点,无额外依赖)
  - 版式沿袭 Streamlit 版视觉(青绿 #009687 主色、深色侧栏、chips、拒答盒);侧栏 `/health` 15s 轮询展示检索策略/chunks/嵌入/生成模型;done 后显示 引用 n/m + 检索/生成/总计 ms + 解析模式 chips
- **端到端实测**(真实 vLLM Qwen3.8-27B + 浏览器):curl 直连 SSE 14 个 delta 帧事件序正确;浏览器实测通过:示例问题点击→流式打字→行内 `[2]` 角标点击展开 chunk 原文→拒答路径(知识库外问题 🚫 拒答盒+引用 0/5)→清空对话回欢迎页;截图存 `docs/web-ui.png`
- **Streamlit 版保留**(按工作流约定,阶段五新前端稳定验收后才删);启动:`uvicorn app.api:app --port 8000` + `cd web && npm run dev`(详见 `web/README.md`)

## 项目 4 Day 24 完成情况(2026-09-14,MCP 化)

- **`app/mcp_server.py`**(官方 SDK mcp 2.2.0,stdio):设计原则与 chatbi 一致——MCP 是传输协议不改工具语义,`search(query, top_k≤10)` 直接复用 `get_retriever()` 混合检索栈(manifest 校验保留);三类原语:tools(search,编号口径与 `build_context` 一致)+ resources(`rag-qa://corpus` 索引/语料统计,manifest 同源)+ prompts(`answer_with_citations` RAG 纪律模板);启动只读配置秒级,嵌入模型首次 search 才加载(~10s 一次);索引错配/top_k 越界转 isError+完整消息回传
- **测试**:新增 `tests/test_mcp_server.py` 2 例(真实 stdio 子进程;索引缺席自动跳过),全量 77 例绿;3 组 query 经 MCP 与本地 `retriever.retrieve` 逐字一致
- **Inspector**:CLI 实测(tools/call 中文 query 命中 background-tasks 正确文档、UTF-8 字节干净);配置 `scripts/mcp-inspector.json`;编码坑实录进 pitfalls(stdout 协议通道恒为 UTF-8,坏字节全来自 `2>&1` 合流的 GBK stderr)
- **双 server 演示 client**(代码在 chatbi 仓 `scripts/mcp_client_demo.py`,依赖其 venv 的 mcp+openai):一次会话连 chatbi-db + rag-qa-docs,工具按 `server.工具` 命名空间路由,vLLM Qwen3.8-27B function calling 编排(temperature=0);内置 3 问实测:数据库题、文档题(带编号引用)、**混合题(同一循环里先 search 文档再 get_schema→execute_sql)**;答案与直连 SQL 核验一致(2014 top3 国家及金额、2013 Consumer 100 张订单)
- requirements.txt 增 `mcp`;README 增「MCP 工具设计」节

## Day 25-26 完成情况(2026-09-14,统一 Landing 页;详见 chatbi 仓 PROGRESS)

- **`D:\LLM_training\portfolio\`**(不建仓库):`index.html` 纯静态单文件(零外部依赖,离线可开)+ `assets/`(chatbi 三张 UI 截图)。rag-qa 在页面中占"项目 1"大块:链路流程图(bge-m3+BM25→RRF→严格 JSON→引用/拒答)、6 指标卡、五轮版本演进表(含两次负结果判决)、关键读数(doc vs chunk 口径发现、增益边际递减、拒答校准、judge 盲评)与工程要点;MCP server 作为"项目 4"与 chatbi-db 并列展示
- 数字全部取自两仓 README/PROGRESS,无新造;本地起站浏览器逐区块截图验收通过
- demo 录制留给用户:页面 demo 区已写四段大纲 + `<video>` 嵌入点(录好放 `portfolio/assets/demo.mp4` 取消注释即可)

## 项目 4 后续(新会话)

1. Day 27-28:简历段落 + 面试题(MCP 高频题素材已就位:两 server 三原语对比、命名空间路由、护栏/拒答纪律在 MCP 下的回传设计);
2. 用户自录 2 分钟 demo 后放 `portfolio/assets/demo.mp4`,取消 index.html 中 `<video>` 注释即嵌入;
3. 可选:双仓 README 交叉链接复核、rag-qa 补 requirements.lock(chatbi 有、本仓无)。

---
## 状态:外部评审四轮全部收口(2026-09-12)✅ → 定位本地运行(部署/frp/转公开取消)→ 主线收口;剩余零散可选项见 `notes/codex-review-2026-09-12.md`

## 外部评审接力入口(2026-09-12)

- Codex 评审了全项目,5 条优先修复已逐条核实(3 属实/1 不复现/1 代码可查属实),
  整理为带优先级的执行清单:**`notes/codex-review-2026-09-12.md`**
- **P0 四项已全部落地(2026-09-12)**:pytest 隔离(裸 pytest 55 全过,不再收集语料库)、
  hybrid 成为代码/示例默认 + lifespan 启动日志、fallback 改安全拒答(v0.2 定版 run fallback 占比 0,
  基线不受影响)、/ask 502 脱敏 + trace_id(完整异常只留服务端日志);真机冒烟通过
  (hybrid 启动日志/chunks 1701/中文 /ask 200 + 4 引用)
- **二次评审 6 项已全部处理(2026-09-12,单测 55→69)**:conftest 临时目录条件回落(本机实测
  repo 内 basetemp 会被系统锁死,不能硬编进 ini)、配置 Literal/范围校验(候选数≥k 上限)、
  /ready(vector/llm 就绪分离)、版本单一来源(app.__version__=0.2.0)、/ask 线程池化+
  Semaphore(4)、索引 manifest 构建写入+启动校验(错配 fail-fast,存量已回填 1701);
  明细见 codex-review 二次评审一节
- **三次评审 5 项已全部处理(2026-09-12,单测 69→74)**:探针加严为完整动作面(建/写/枚举/删)、
  manifest 增嵌入模型绑定(换模型不重建即拒启)、manifest 按 collection 分文件并下沉 get_retriever
  按模式路由(parentchild 校验 pc 库,实测通过)、/ready 探活线程池化、Dockerfile LABEL 版本对齐;
  三模式冒烟:hybrid 全链路 ✓ / parentchild 双路校验 ✓ / 换模型与篡改 pc manifest 均 fail-fast ✓
- **四次评审单项已修(2026-09-12,单测 74→75)**:temp 探针从"测根"改测 pytest 实际用的
  `pytest-of-<user>` 子树(评审沙箱挂的真因),回落候选轮转(.pytest_tmp→2→3)防锁死目录毒害;
  忠实演练(默认根硬指文件=探测必败)下裸 pytest 75 全绿并正确回落,详见 codex-review 四次评审一节
- **UI 视觉升级(2026-09-12)**:app/ui.py 重做——品牌青绿主题+渐变标题、深色侧栏(服务状态/清空对话/
  版本)、卡片式聊天气泡(用户/AI 双色)、指标徽章(引用/检索/生成/解析)、引用展开美化(青绿竖线+
  文档名徽章+语法高亮代码)、空状态欢迎卡+6 个一键示例问题、隐藏 Streamlit 原生工具栏;
  浏览器实测全链路(示例提问→回答带引用→展开 chunk 原文→刷新保历史)
- 定位:从实验型项目收口为可稳定部署、可持续回归的服务(P0 半天/P1 1~2 天)
- 明确不做:rerank/rewrite 进主线(保持实验开关)

## 已定决策

| 项 | 决定 |
|---|---|
| 语料 | FastAPI 官方中文文档（GitHub docs/zh/docs；决策时估约 150 篇，实际清洗后入库 122 篇） |
| 仓库 | 独立仓库 LyZheFeng/rag-qa（保持私有；原"终稿后转公开"已随部署取消，2026-09-12） |
| 生成模型 | 内网 vLLM `http://10.14.6.55:30561/v1`，`Qwen3.8-27B`，key=1234，`enable_thinking:false`，已验证可用 |
| 嵌入/重排 | 本地 bge-m3 + bge-reranker-v2-m3（HF_HOME=D 盘，hf-mirror 下载；reranker Phase 4 前再下） |
| 部署 | **本地运行即可**(2026-09-12 用户拍板,原"学生机 Docker + frp"取消;Docker 文件留档备用) |
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
- [x] 生成契约：`{answer, citations, refused}` 严格 JSON；剥围栏/`</think>` 后取首 `{` 末 `}`；解析失败重试 1 次（带纠正提示），再失败降级纯文本（2026-09-12 起 P0 改为安全拒答）；`parse_mode` 记录 json/retry/fallback
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
- [x] v0.3-rerank **搁置**(2026-09-11):检索层验证在 CPU+电池供电下 75 分钟未跑完(每题 >20s,比 hybrid 慢两个数量级),环境不可行;代码/开关保留,GPU 机器可重启;教训入 pitfalls(离线脚本要增量输出,重模型先 10 题实测耗时)
- [x] v0.3-rerank **接电重跑完成**(2026-09-11,tag `v0.3-rerank`):检索层 chunk recall@5 90%/MRR 0.751,但端到端正确性仅 +0.08(4.49),CPU 每题 +6.3s → **默认版本保持 v0.2-hybrid**,v0.3 留给 GPU 场景;retrieval_check 已改造为增量落盘+断点续跑(电池中断零损失验证有效)
- [x] v0.4-rewrite **负结果收口**(2026-09-11):平权 RRF 74.4%/原查询加权 80.0%,均低于 v0.2 的 83.1%;机理=变体共识稀释原查询排序,教训=小样本探测只判耗时、质量结论必须全量;代码保留
- [x] v0.5-chunking **收官**(2026-09-11):三案 doc 口径差距 ≤1.3pp(heading 94.4/fixed 95.6/parentchild 95.0),parent-child 快评 4.64 vs v0.2 的 4.62 打平——**切块不是瓶颈**,heading-512-50 保持现役;FixedChunker 触底退化 bug 修复入单测
- [x] 30 条一致性抽样 **以跨模型盲评完成**(2026-09-11):独立第三方模型 vs Qwen judge,±1 一致率 100%(24/24)、Pearson 0.886,三个误拒样本被独立同判;judge 可信度验证通过,入 results.md(人工打分文件保留,用户随时可补)
- [x] Phase 5 拒答校准(2026-09-11,commit 59722e7):分数阈值闸门原理性失效(无法答题 top-1 中位 0.94,与可答题分布重叠),LLM 内容级拒答工作点(误拒 7.5%/正确拒答 100%)支配全曲线,双指标达标,**维持现状**;`eval/calibration.md` 留档
- [x] Phase 6 **备战完成**(2026-09-11):Dockerfile/compose/dockerignore + README 终稿;
  本机 Docker 全链路验证通过(build → 首启自动下载 bge-m3 → hybrid 1701 chunks → /health OK →
  /ask 端到端 2.8s → UI 200)。途中修三个潜伏 bug:compose 注入宿主机 HF_HOME、
  embed.py 强制 HF_HUB_OFFLINE 挡首启下载、/health 写死 vector 检索器属性(v0.2 起潜伏)
- [x] Phase 6 部署 → **转为本地运行定位**(2026-09-12 用户拍板"本地能跑就行",frp/公网验收/转公开取消)。
  2026-09-11 已回收全部 Docker 产物,D 盘恢复至 671.9GB(prune + vhdx 稀疏压缩 9.36→1.86GB +
  注销 docker-desktop WSL 发行版并删 vhdx);Dockerfile/compose 留档在库,README 快速开始已改为本地裸跑流程

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

主线已收口:v0.2-hybrid 定版 + 本地运行定位 + 两轮评审修复完毕(2026-09-12)。剩余均为可选项,按需再做:

- **P1 尾巴**:extract_json 长度上限 + schema 白名单字段(其余 P1 项已被二次评审处理吸收)
- **P2 评估增强**(可选):指标拆分、200 题回归触发脚本

### 今日评估链路备忘

- 全量 200 题 ≈ 40 分钟(每题 5 次 LLM 调用);快评 50 ≈ 12 分钟
- 无检索对照列同题复跑完全一致(3.86),judge 复现性良好
- eval/runs/ 已留档 3 个 run(v0.1-smoke/v0.1-full/v0.2-full)

## 环境备忘

- Python 3.13.9（D:\python），venv 在 `.venv/`
- D 盘剩 ~672GB（2026-09-11 Docker 产物回收后 671.9GB），无空间压力；HF/pip 缓存全部指向 D 盘
- Git Bash 中文坑：curl 中文乱码 → 一律 Python + UTF-8
- GitHub https 偶发重置：失败重试
