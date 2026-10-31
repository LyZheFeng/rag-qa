# rag-qa 语料、切块与评估耗时分析

> 内容：语料规模、块/chunk 大小分布、切块算法与段落边界行为，以及 200 题跑批的单题耗时构成。
> 数据来源：`data/raw/fastapi-zh/`、`data/chunks/chunks.jsonl`、`pipeline/{loader,chunker}.py`、`eval/runs/*/records.jsonl`
> 统计方式：脚本直接读取上述文件实算，非转述 README；可复现命令见文末附录。
> 快照：122 篇语料 / 1,701 chunk（索引 `fastapi_zh_v1`，与 manifest 一致）。

---

## 0. 结论摘要

- 语料 **122 篇、677 KB、42.1 万字符**（清洗后 50.0 万），**其中 48.8% 是代码**。
- 切成 **1,701 个 chunk**，**中位 298 字符 / 137 token**，上限 **512 字符**（不是 token），每篇平均 13.9 块。
- 切法是「**标题感知 + 段落原子打包 + 50 字符重叠**」：默认在**段落边界**断开；只有 3% 的超长代码块按行内切；32% 的 chunk 开头带上一块的 50 字符尾巴。
- 4.0% 的字符因「文档内重复代码块去重」未被任何 chunk 覆盖，属有意去重，不是丢字。
- 评估跑批：单题约 **12 秒**（真正答题只占 1.2s，其余是评估开销），200 题一轮约 **40 分钟**，三轮约 2 小时。

---

## 1. 语料规模

| 指标 | 值 |
|---|---|
| 纳入文档 | **122 篇**（目录下 124 个 `.md`，排除 `_llm-test.md`、`translation-banner.md`） |
| 磁盘体积 | **677 KB** |
| 原始正文字符 | **421,173** |
| 清洗后字符（代码占位符已还原） | **500,019** |
| 单篇中位 / 均值 | 2,310 / 3,449 字符 |
| 单篇 p90 / 最大 | 7,438 / **18,688**（`index.md`） |
| 单篇最小 | 35 字符（`resources/index.md`） |
| 代码块字符占比 | **48.8%** |

最大的 3 篇：`deployment/docker.md`（18,688 字）、`index.md`、`async.md`。
最小的 3 篇：`resources/index.md`（35 字）、`about/index.md`（38 字）、`learn/index.md`（100 字）。

> 为什么清洗后反而更大：原文里的代码以占位符形式存在，`cleaner` 会从 FastAPI 源码仓还原真实代码（共 439 处），所以正文字符从 42.1 万涨到 50.0 万。

---

## 2. 块（block）级统计

「块」是 loader 的切分单位，也是打包时的原子，定义见 `pipeline/loader.py:3`：

- **一个代码围栏整体算一块**（`kind=code`），不拆；
- **其余以空行分段**，一段一块（`kind=text`）；
- `full_text` 由各块以 `\n\n` 连接，块的 `char_span` 落在 `full_text` 上，可逐字回溯。

| 指标 | 值 |
|---|---|
| 块总数 | **5,554** |
| 块大小中位 | **46 字符** |
| 块大小均值 / p90 | 88 / 170 字符 |
| 最大块 | 3,600 字符（`deployment/server-workers.md` 的代码块） |
| > 512 字符的块 | **166 个（3.0%）**，按行切分 |

块大小分布：

| 区间 | 数量 | 占比 |
|---|---|---|
| ≤ 128 字符 | 4,841 | 87.2% |
| 129–256 | 330 | 5.9% |
| 257–512 | 217 | 3.9% |
| > 512 | 166 | 3.0% |

---

## 3. Chunk 级统计

| 指标 | 字符 | bge-m3 token |
|---|---|---|
| 最小 | 13 | 9 |
| p25 | 153 | 79 |
| **中位** | **298** | **137** |
| p75 | 459 | 181 |
| p95 | 504 | 244 |
| **最大** | **512** | 348 |

- chunk 总数 **1,701**；每篇均值 **13.9**（中位 11，最多 46，最少 1）。
- chunk 字符总量 **502,869**（含重叠重复），嵌入 token 总量 227,231。
- **512 是字符上限，不是 token**：`scripts/build_index.py:65-66` 的 `--size 512 --overlap 50` 都是字符。
- 实际 token 中位仅 137，远低于 bge-m3 的 8192 上限，**不存在嵌入截断**。
- 有 **227 个 chunk（13.3%）不到 100 字符**（短小节、短代码块）；只有 **9 个**正好顶到 512。

### 3.1 章节深度

| 标题链层级 | chunk 数 |
|---|---|
| 1 层 | 150 |
| 2 层 | 950 |
| 3 层 | 530 |
| 4 层 | 65 |
| 5 层 | 6 |

> 2 层占 56%：大部分内容是「大类 > 小节」结构，标题链本身就带定位信息，这也是 BM25 把 `section_path` 一起建索引的原因（`app/hybrid.py:90`）。

---

## 4. 切块算法

### 4.1 第 1 步：切块（loader）

```
md → clean_markdown（去噪声、还原代码） → parse_blocks
   → 代码围栏 = 1 块；其余按空行分段 = 1 块
   → 每块带 (heading_path, kind, text, char_span)
```

### 4.2 第 2 步：打包（`HeadingAwareChunker`，`pipeline/chunker.py`）

1. **标题路径一变就开新组**，chunk 永不跨标题组合（`chunker.py:8`、`:151-158`）；
2. 组内把块当原子，**贪心塞到 512 字符**（`chunker.py:167-188`）；
3. 溢出时把当前块收尾，取上一块**最后 50 字符**作为新块开头（滚动重叠，`chunker.py:174-183`）；
4. 单块 > 512 字符时**按行切**成 ≤512 的片段，片段间以 `\n` 相接（`chunker.py:121-144`）；
5. 文档内按内容 hash **去重**（跨文档不去重），并重排 `seq`（`chunker.py:190-200`）。

### 4.3 不变量

`chunk.text == full_text[char_span[0]:char_span[1]]`，且 `char_end - char_start == len(text)`。
这样前端「引用卡片展开原文」可以直接用 `char_span` 切原文，不用二次检索。

---

## 5. 边界行为：段落间切还是段落中切？

**主路径是段落间**：块是原子，普通段落的 chunk 一定在段落边界收尾，不会把一段话从中间劈开。

三个例外：

| 情况 | 是否切断段落 | 说明 |
|---|---|---|
| 正常打包（97% 的块） | 否 | 整段放入，或整段滚到下一个 chunk |
| 超长块（166 个，3%） | **是**，按行切 | 长代码块被拆成几片；**不切断行**，只切行间 |
| 50 字符重叠 | 只影响**开头** | 下一个 chunk 的头部是上一块尾部的 50 字符，**可能从句子中间开始**（重叠，不是丢失） |

### 5.1 实测边界统计（1,579 对相邻 chunk）

| 情况 | 对数 | 占比 |
|---|---|---|
| 有重叠（下一个起点落进上一个内部） | 506 | **32.0%** |
| 无重叠 | 1,073 | 68.0% |

- 重叠长度稳定在 **50 字符**（中位 50.0，均值 49.4，最大 50），与配置一致。
- 无重叠的 1,073 对里：**1,000 对间隙正好 2 字符**（就是原文的 `\n\n` 段落分隔符），34 对间隙 1 字符，其余 39 对间隙较大。
- 39 对大间隙合计跳过 **20,137 字符（占全语料 4.0%）**。逐条核查过：**全部是同一文档内重复出现的代码块/示例被 hash 去重**，对应内容在文档前部已有 chunk，不是切块丢字。

### 5.2 一个典型例子

`advanced/advanced-dependencies.md` 里同一段 `FixedContentQueryChecker` 代码出现了 4 次，去重后只保留必要副本，于是相邻 chunk 之间会出现 440 字符的「空档」——但该文本在文档其他 chunk 中完整存在。

---

## 6. 对检索/生成的影响与取舍

1. **代码占一半**：BM25 的 ASCII 整词 + 中文 bigram 设计（`app/hybrid.py:20-36`）正好补向量对标识符不敏感的短板，这是 v0.2 从 64% → 83% chunk recall 的主要来源。
2. **中位 298 字符偏小**：好处是定位准；代价是单块上下文有限，长答案要靠 top-5 拼接。v0.5 的 parent-child 实验（整节喂生成）在 50 题上与现役打平、faithfulness 还略降，因此没有换方案。
3. **512 字符 ≈ 137 token**：远没用满 bge-m3 的上下文窗口。v0.5 对比过 fixed-512 与 heading 切法，doc 口径 recall 差距 ≤1.3pp，说明**切块不是瓶颈**，保留标题结构更划算。
4. **13% 的 chunk < 100 字符**：短块（如一行小标题、短代码）单看信息量低，但它们是标题链和示例的重要补充；BM25 排序时会被更长、更匹配的块压下去，实际影响有限。
5. **4% 去重**：刻意为之，避免同一代码示例占据多个 top-5 名额；代价是「文档覆盖率」不是 100%，做召回分析时要意识到这一点。

---

## 7. 可复现

### 7.1 关键文件

| 文件 | 内容 |
|---|---|
| `pipeline/loader.py` | 块定义、`full_text` 与 `char_span` |
| `pipeline/chunker.py` | `HeadingAwareChunker` / `FixedChunker` |
| `scripts/build_index.py` | `--size 512 --overlap 50` 默认值 |
| `data/chunks/chunks.jsonl` | 1,701 条，字段 `chunk_id/doc_name/seq/section_path/text/char_span/n_chars/hash` |
| `data/chunks/stats.md` | 原有 chunk 统计（字符/token 直方图） |

### 7.2 复算脚本

```python
# 在仓库根目录执行：.venv/Scripts/python.exe -X utf8
import json, statistics as st
from collections import defaultdict, Counter
from pathlib import Path
from pipeline.loader import load_doc, iter_corpus
from pipeline.config import get_settings

root, s = Path("."), get_settings()

# 1) 文档规模
docs = iter_corpus(s.corpus_root)
chars = [len(p.read_text(encoding="utf-8")) for p in docs]
print(len(docs), sum(chars), st.median(chars), max(chars))

# 2) 块规模（含超长块占比）
sizes, kinds = [], Counter()
for p in docs:
    d = load_doc(p, s.corpus_root, s.docs_src_root)
    sizes += [len(b.text) for b in d.blocks]
    kinds.update(b.kind for b in d.blocks)
print(len(sizes), st.median(sizes), sum(1 for x in sizes if x > 512))

# 3) chunk 规模 + 边界重叠
chunks = [json.loads(l) for l in (root/"data/chunks/chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
n = [c["n_chars"] for c in chunks]
print(len(chunks), st.median(n), max(n), sum(1 for x in n if x < 100))

by = defaultdict(list)
for c in chunks: by[c["doc_name"]].append(c)
pairs = ov = 0
for d, cs in by.items():
    cs.sort(key=lambda x: x["seq"])
    for a, b in zip(cs, cs[1:]):
        pairs += 1
        if b["char_span"][0] < a["char_span"][1]:
            ov += 1
print(pairs, ov, f"{ov/pairs:.1%}")
```

---

## 8. 跑批耗时（题库评估）

> 口径：`DeepSeek-V4.1-Flash` 答题 + `Qwen3.8-27B` 判题，hybrid 检索 `k=5`，`temperature=0`。
> 每题 = **1 次本地检索 + 5 次大模型调用**（答题 1、无检索对照 1、correctness 判分 2、faithfulness 1）。
> 样本：2026-10-31 第 1 轮全量 200 题（事实 100 / 推理 60 / 无法回答 40），实测墙钟 **37.3 分钟**。

### 8.1 单题构成（`fact-001` 逐环节实测）

| 环节 | 次数 | 实测耗时 |
|---|---|---|
| 本地检索（bge-m3 + Chroma） | 1 | **0.16s** |
| DeepSeek 答题 | 1 | **1.76s** |
| DeepSeek 无检索对照 | 1 | **3.78s** |
| Qwen 判分（答题） | 1 | **2.02s** |
| Qwen 判分（无检索对照） | 1 | **3.08s** |
| Qwen 拆 claim 算 faithfulness | 1 | **6.24s** |
| **合计** | | **17.05s** |

> 这是偏慢的一题（答案较长、claim 拆得多）。全量均值见下。

### 8.2 分题型实测

| 题型 | 样本 | 均值 | 中位 | 区间 | 其中生成 | 其中检索 |
|---|---|---|---|---|---|---|
| 事实题 | 100 | **12.1s** | 11.8s | 4.3 – 20.5s | 1.2s | 69ms |
| 推理题 | 60 | **16.2s** | 16.1s | 6.3 – 25.9s | 1.4s | 78ms |
| 无法回答题 | 40 | **1.4s** | 1.1s | 0.8 – 10.0s | 1.1s | 70ms |
| **全部** | **200** | **11.2s** | 11.8s | p90 19.2s | — | — |

无法回答题快，是因为模型直接拒答，**不触发**无检索对照与 quality 判分（只算 answer 那次调用）。

### 8.3 每轮与三轮估算

```
100 事实 × 12.1s + 60 推理 × 16.2s + 40 无法回答 × 1.4s
≈ 1210 + 972 + 56 ≈ 2240s ≈ 37 分钟
```

第 1 轮实测墙钟 **37.3 分钟**（13:17:49 → 13:55），与估算吻合。三轮全量合计约 **1 小时 50 分**。

### 8.4 为什么「答题」只占 10%

12 秒里真正生成答案只有 1.2 秒，其余 ~10.8 秒全是**评估开销**：

1. **无检索对照**（3.8s）：同题再问一次裸模型，证明 RAG 增益；
2. **两次 correctness 判分**（2.0s + 3.1s）：一份给 RAG 答案，一份给对照答案；
3. **faithfulness**（6.2s，最慢）：把答案拆成最多 8 条声明逐条核对。

判分开不开思考影响很大：Qwen 对 `thinking` 字段不认账（8.0s / 170 token），改用 `chat_template_kwargs` 后 **1.8s / 39 token**。这也是 `JUDGE_EXTRA_BODY` 单独配置的原因。

### 8.5 想更快的话，代价是什么

| 做法 | 单题耗时 | 代价 |
|---|---|---|
| 现状（全量口径） | ~12s | — |
| 判分调用并行 | ~5s | 端点并发压力上升，限流时更容易整题失败 |
| faithfulness 只抽样 | ~6s | faithfulness 变成子集口径，不能与旧行直接比 |
| 不跑无检索对照 | ~8s | 失去「RAG 增益」这条最关键的证据 |

结论：**正式跑批不建议砍**；要快评就另起一个脚本，并明确标注口径不同。

### 8.6 复现

`records.jsonl` 每题都记了 `elapsed_s`（整题）、`retrieve_ms`、`generate_ms`：

```python
import json, statistics as st
from pathlib import Path

recs = [json.loads(l) for l in Path("eval/runs/<run>/records.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
for t in ("fact", "reasoning", "unanswerable"):
    rs = [r for r in recs if r["type"] == t]
    e = [r["elapsed_s"] for r in rs]
    print(t, len(e), round(st.mean(e), 1), round(st.median(e), 1))
```

---

## 9. 备注

- 本文件只描述**现役索引**（`heading-512-50`）；`chunks_fixed.jsonl`（fixed 切法）和 `chunks_pc*.jsonl`（parent-child）是 v0.5 的对比实验产物，未用于线上检索。
- 文中 token 数来自 `data/chunks/stats.md` 的 bge-m3 tokenizer 统计；字符数由本次实算，两者口径不同，不要混用。
- 若后续重建索引（换语料或改 `--size/--overlap`），本文件的数字需重跑第 7.2 节脚本更新。