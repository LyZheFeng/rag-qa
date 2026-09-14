# rag-qa · FastAPI 中文文档问答系统

基于官方 FastAPI 中文文档(122 篇)的检索增强问答:混合检索(BM25 + 向量)定位段落,
LLM 依据资料作答并逐句标注引用,资料不足时诚实拒答而非编造。

> Agent 应用开发备考 · 项目 1(对应 `agent-internship-plan.md` Week 1~2)

**最终版本 v0.2-hybrid**:正确性 4.41/5(judge 评分,经独立模型盲评验证)、误拒率 7.5%、
无法回答题正确拒答率 100%、答案忠实度 96%。

## 架构

```
用户提问
   │
   ▼
┌─ 检索(v0.2-hybrid,单题 <0.3s)──────────────────┐
│  bge-m3 向量 top-20 ─┐                           │
│                      ├─ RRF 融合 → top-5 chunk   │
│  BM25 中文bigram+代码词 ┘                         │
└──────────┬────────────────────────────────────┘
           ▼
┌─ 生成(Qwen3.8-27B,内网 vLLM)──────────────────┐
│  编号上下文 → 严格 JSON {answer, citations,      │
│  refused};解析失败重试 1 次 → 安全拒答           │
└──────────┬────────────────────────────────────┘
           ▼
  回答 + 引用卡片(可展开 chunk 原文) 或 拒答说明
```

- **语料管道**:md 加载 → 占位符还原真实代码(439 处)→ 清洗 → 标题感知切块(512/50)
  → 1701 chunk 入 Chroma;不变量 `chunk.text == full_text[char_span]` 全库校验
- **评估体系**:200 题测试集(事实 100 / 推理 60 / 无法回答 40,gold chunk 标注),
  recall@5 双口径 / MRR / judge 正确性 / faithfulness 拆 claim / 拒答率分口径统计,
  另设"无检索直接问答"对照列证明 RAG 增益

## 快速开始(本地运行)

```bash
# 1) 环境(Python 3.13)
python -m venv .venv
.venv\Scripts\activate           # Windows;Linux/macOS 为 source .venv/bin/activate
pip install -r requirements.txt

# 2) 配置:LLM 指向内网 vLLM;模型缓存指到本机有空间的盘
cp .env.example .env             # 填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL,并把 HF_HOME 改成本机实际路径

# 3) 模型与索引(仅首次;data/chroma/ 不入库,新环境要重建)
python scripts/download_models.py --embed   # bge-m3 ~2.1GB,走 hf-mirror
python scripts/build_index.py               # 122 篇 md → 1701 chunk → Chroma(CPU 约 6min)

# 4) 起服务
python -m uvicorn app.api:app --port 8000   # API:http://localhost:8000/docs
streamlit run app/ui.py                     # UI :http://localhost:8501
```

说明:生成依赖内网 vLLM,需能访问 `10.14.6.55`;检索/嵌入完全本地——LLM 不通时
/health 仍正常、/ready 报 `llm_ready:false`、/ask 返回 502(客户端只见脱敏文案+追踪 id,
细节在服务端日志)。单测:`pytest`(75 个,全部离线;系统临时目录的 `pytest-of-*` 子树不可用的
受限环境会自动回落到项目内目录)。

Docker 部署文件(Dockerfile/docker-compose.yml)留档在库备用,本地运行用不上。

## 版本演进与评估(200 题全量真实跑批)

| 版本 | 正确性 | 误拒率 | 正确拒答率 | chunk recall@5 | 延迟代价 | 判决 |
|---|---|---|---|---|---|---|
| v0.1-baseline 纯向量 | 3.92 | 18.1% | 97.5% | 64.4% | — | 基线 |
| **v0.2-hybrid BM25+RRF** | **4.41** | **7.5%** | **100%** | **83.1%** | +0.1s | **✅ 定版** |
| v0.3-rerank CrossEncoder 精排 | 4.49 | 5.6% | 97.5% | 90.0% | +6.3s/题 | CPU 不划算,留 GPU 场景 |
| v0.4-rewrite 多查询扩展 | —(检索层出局) | — | — | 74.4% | +1.8s/题 | 变体共识稀释排序,负结果 |
| v0.5-chunking 三案对比 | 持平 | — | — | 94~96%(doc 口径) | — | 切块非瓶颈,负结果 |

关键读数:

- **v0.1 的教训**:doc 口径 recall 87.5% 但 chunk 口径仅 64.4%——找对文档、找不到段落;
  29 道误拒里 28 道根因是 gold chunk 没进 top-5(检索没送到,不是模型不会)
- **v0.2 一轮吃掉大头**(+0.49 正确性);v0.3 检索层再 +6.9pp 但端到端只 +0.08
  ——排序增益对"top-5 已够用"的生成是冗余的
- **推理题翻身**:v0.1 时被检索拖累(3.66 vs 裸模型 4.17),v0.2 追平(4.12);
  事实题 RAG 增益 +0.87
- **拒答机制**:分数阈值闸门原理性失效(无法答题 top-1 匹配分中位 0.94,与可答题分布
  重叠),LLM 内容级拒答支配全阈值曲线,维持自主拒答(`eval/calibration.md`)

评估可信度:judge 与独立第三方模型盲评对比,±1 分一致率 100%(24/24),Pearson 0.886,
误拒样本被双方独立同判;完整数据见 [`eval/results.md`](eval/results.md),
原始记录留档 `eval/runs/`。

## 踩坑 Top 3

1. **rank-bm25 0.2.2 + NumPy 2.x 静默返回全 0 分**——`get_scores()` 对明显命中的查询
   返回全零且不报错。最小复现确认后自实现 30 行 Okapi BM25(倒排表)。
   教训:第三方"标准库"也要冒烟验证再信。
2. **HF_HOME 不生效,2.1GB 模型下到 C 盘**——直接 import sentence_transformers 的脚本
   没先应用项目配置,HF_HOME 落空走默认路径。教训:环境变量型配置必须在 import 模型库
   之前应用;重模型脚本先 10 题实测耗时再全量。
3. **多查询 RRF 平权融合被变体共识稀释**——3 个 LLM 变体对"相关但不准"chunk 的共识分
   轻松压过原查询第一名,recall 反降 8.7pp。教训:多路融合必须明确"谁有否决权";
   小样本(10 题)探测只能判断耗时,质量结论必须全量。

## 目录

```
app/        检索(hybrid/rerank/rewrite/parentchild 开关)· 生成 · 编排 · API · UI · MCP server
pipeline/   语料加载 / 清洗 / 切块 / 嵌入 / 入库
eval/       出题 · 预筛 · 跑批 · 指标 · 校准 + results.md / calibration.md
data/       语料 / chunk / Chroma / 评估产物(模型缓存不入库)
tests/      77 个单测(离线 75 + 真实索引 MCP 协议 2)
```

## MCP 工具设计(项目 4 Day 24,官方 SDK `mcp` 2.x,stdio transport)

设计原则与 chatbi 的数据库查询 server 一致:**MCP 是工具的传输协议,不改工具的语义**。
`app/mcp_server.py` 直接复用 `get_retriever()` 的混合检索栈(模式随 .env 的
`RETRIEVER`,默认 hybrid,含 manifest 索引校验),RAG 生成(编号上下文、引用、
拒答)留在客户端。

| 原语 | 定义 | 谁来调用 | 为什么用它 |
|---|---|---|---|
| **tools** | `search(query, top_k≤10)` | 模型,带参数 | 编号 chunk 列表,编号口径与主链路 `build_context` 一致,客户端直接沿用引用纪律 |
| **resources** | `rag-qa://corpus` | 客户端,按 URI 读 | 索引/语料统计(manifest 同源:检索模式、chunk 数、文档清单,数值随索引重建更新),静态上下文不占工具轮次 |
| **prompts** | `answer_with_citations(question)` | 用户主动触发 | "忠于检索内容、编号引用、不足即拒答"的 RAG 纪律模板,与主链路 SYSTEM_PROMPT 同源 |

启动只读配置(秒级),嵌入模型/索引在首次 `search` 才加载(~10s,进程内只付一次)
——Inspector 里 tools/list 即时可见。索引校验失败(manifest 错配)转 `isError=true`
+ 完整诊断消息回传;`top_k` 越界同样以 isError 报告参数边界。

验证(`tests/test_mcp_server.py`,2 例,真实 stdio 子进程):三类原语发现与调用、
参数边界、**3 组 query 经 MCP search 与本地 `retriever.retrieve` 逐字一致**;
Inspector CLI 实测通过(中文 query 命中正确文档,UTF-8 字节干净)。
演示见 chatbi 仓 `scripts/mcp_client_demo.py`:一次会话连两个 server
(chatbi-db + rag-qa-docs),vLLM agent 按命名空间路由工具调用。

```bash
# 运行(stdio)与 Inspector 调试
.venv/Scripts/python.exe -m app.mcp_server
npx @modelcontextprotocol/inspector --cli --config scripts/mcp-inspector.json --server rag-qa-docs --method tools/call --tool-name search --tool-arg "query=后台任务怎么用" --tool-arg "top_k=2"
```

## 运行版本开关(.env)

`RETRIEVER=vector|hybrid|rerank|rewrite|parentchild`(默认 hybrid);
rerank 需 bge-reranker-v2-m3(CPU 每题 +6.3s,建议 GPU 环境)。
