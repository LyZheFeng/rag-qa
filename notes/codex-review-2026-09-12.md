# 外部评审(Codex,2026-09-12)→ 优化待办

> 新会话从这里接力。评审原文要点 + 本机核实结果 + 执行优先级。
> 背景:六 Phase 已收官(v0.2-hybrid 定版,正确性 4.41/误拒 7.5%/正确拒答 100%/faithfulness 96%,
> 见 eval/results.md)。本评审的定位:**从实验型项目收口为可稳定部署、可持续回归的服务**。
> (2026-09-12 更新:项目定位其后调整为本地运行、部署取消,"可稳定部署"目标作废,
> P1 工程加固相应弱化为可选项,按需再做。)

## 评审主张核实(2026-09-12 本机验证)

| # | 评审主张 | 核实 | 说明 |
|---|---|---|---|
| 1 | 裸 pytest 收集语料库测试,323 错误 | ✅ 属实 | `pytest --collect-only` 复现:1324 外来测试 + 323 收集错误(data/raw/fastapi-docs-src);我此前一直 `pytest tests` 未暴露 |
| 2 | tests/ 41 过 13 错(Windows 临时目录权限) | ⚠️ 本机不复现 | 本机稳定 54 全过;系 Codex 沙箱环境产物。`--basetemp` 防御仍值得做 |
| 3 | 默认配置与 README 不一致 | ✅ 属实 | config.py 与 .env.example 默认 `vector`,README 宣称 hybrid 定版;新克隆会静默跑 v0.1 |
| 4 | fallback 降级不安全 | ✅ 属实 | generator.py:139 两次解析失败后原文当答案且 refused=False |
| 5 | API 错误暴露内部异常 | ✅ 属实 | api.py 502 detail 含异常类型+完整消息 |

## 执行清单(按评审优先级,核实后确认可行)

### P0 修复(半天)—— ✅ 已完成(2026-09-12,全库 55 单测过 + 真机冒烟)

1. **pytest 隔离** ✅:`pytest.ini`(testpaths=tests / norecursedirs / -p no:cacheprovider)落地,
   裸 `pytest` 从 1324 外来测试 + 323 收集错误 → 干净收集 55 条全过;`--basetemp=.pytest_tmp`
   验证可用,.gitignore 已补 `.pytest_cache/`+`.pytest_tmp/`(CI 接入时统一带 basetemp)。
2. **统一 hybrid 默认** ✅:config.py 默认 `retriever="hybrid"`、.env.example 同步;
   lifespan 启动日志一行摘要(实测:`retriever=HybridRetriever | embed=BAAI/bge-m3 (BgeM3Embedder, dim=1024)
   | collection=fastapi_zh_v1 | chunks=1701 | llm=Qwen3.8-27B`);/health 下钻逻辑抽为 `_vector_core` 复用。
   核实过:tests/ 无任何用例依赖 vector 默认(全用 fake),无需改。
3. **fallback 改安全拒答** ✅:两次解析失败 → `refused=True` + 固定提示语"生成结果格式异常,无法给出可靠回答,请重试。",
   parse_mode 仍记 fallback;核实 v0.2-hybrid 定版全量 run parse_mode=fallback 占比 0(200/200 json),基线数字不受影响。
4. **API 错误脱敏** ✅:502 detail 只回 `{"message": "生成服务暂时不可用", "trace_id": <12位>}`,
   完整异常(traceback)走服务端 `uvicorn.error` 日志,凭 trace_id 可回查;新增单测断言响应不含异常类型/内网细节。

1. **pytest 隔离**:加 `pytest.ini`:
   ```ini
   [pytest]
   testpaths = tests
   norecursedirs = data .venv
   ```
   顺手:`addopts = -p no:cacheprovider`(避免根目录写 .pytest_cache)。
   CI/脚本统一 `--basetemp=.pytest_tmp`(应对 #2 的环境差异)。
2. **统一 hybrid 默认**:config.py `retriever: str = "hybrid"`、.env.example 同步;
   启动日志(lifespan)打印实际检索器类型、模型、collection 与 chunk 数。
   同步更新受影响单测(目前部分测试隐含 vector 默认)。
3. **fallback 改安全拒答**:generator.py 降级路径改为 `refused=True` +
   answer="生成格式异常,无法给出可靠回答"(parse_mode 保留 fallback 标记用于观测);
   评估基线数字不受影响(v0.2 全量 run 中 parse_mode=fallback 占比 0,见 eval/runs)。
4. **API 错误脱敏**:服务端 log 完整异常,客户端只回 `{"detail": "生成服务暂时不可用"}` + 追踪 id。

### 二次评审 6 项 → ✅ 已处理(2026-09-12,全库 69 单测过 + 真机冒烟)

1. **默认 pytest 命令** ✅(方案调整):未照建议把 basetemp 硬编进 pytest.ini——本机实测
   repo 内 basetemp 会在启动清理阶段被系统拒绝访问(残留目录甚至无法删除),后续运行全挂;
   改为根 `conftest.py` 启动探测:系统临时目录不可写(评审沙箱的场景)才回落 `.pytest_tmp`,
   可写则保持 pytest 原生行为。两种环境裸 `pytest` 均绿。
2. **配置约束** ✅:`retriever` 改 Literal 五枚举,`hybrid_candidates` Field(ge=API_MAX_K=10)
   (候选深度小于 API k 上限会融合不足 k 条),`rrf_k` ge=1;非法配置启动即 ValidationError。
3. **readiness** ✅:新增 `GET /ready`——vector_ready(库有数据)+ llm_ready(3s 轻量 ping),
   任一不就绪 503;/health 保持便宜(不碰 LLM)作存活探针,二者分工写进 api.py 模块注释。
4. **版本单一来源** ✅:`app/__init__.py` 定 `__version__="0.2.0"`,FastAPI(version=) 与
   /health 均引用,启动横幅也带版本号。
5. **同步阻塞** ✅:/ask 改 async + `run_in_threadpool`(embedding+LLM 不再占事件循环),
   `Semaphore(4)` 并发上限,打满返回 503"服务繁忙";单测覆盖饱和路径。
6. **索引 manifest** ✅:新增 `pipeline/manifest.py`——build_index 主线构建写入
   (chunks.jsonl sha256 / 条数 / collection / 嵌入模型,实验 tag/collection 不写防污染);
   启动时校验哈希+collection+Chroma 条数,错配 **fail-fast**(实测篡改哈希后启动即拒,
   发生在模型加载前);存量索引已回填 manifest(1701 chunks,自检 ok),旧索引无 manifest
   时警告放行不拒启。

### 三次评审 5 项 → ✅ 已处理(2026-09-12,全库 74 单测过 + 三模式真机冒烟)

1. **默认 pytest 仍不稳** ✅(按第二建议):conftest 探针从"只建删文件"加严为完整动作面
   (建子目录→写文件→scandir 枚举→删文件→删子目录),"可建不可枚举"的受限沙箱不再误判。
   未采纳"ini 硬编 basetemp":本机实测 repo 内 basetemp 会被系统锁死导致后续全挂(见二次评审 #1)。
2. **manifest 未校验嵌入模型** ✅:check_manifest 增参 embed_model,不一致 → mismatch 拒启
   (实测换 EMBED_MODEL 启动即拒,提示"向量不可混用")。
3. **parentchild 索引绑定错位** ✅:manifest 改为**按 collection 分文件**(manifest.{collection}.json),
   校验下沉到 get_retriever 并按模式路由——parentchild 严格校验 fastapi_zh_pc+chunks_pc.jsonl(实测通过),
   父块仅文件级校验主库(免条数比对,该模式不查询主 collection);其余模式校验主库。
   build_index 守卫随之简化(任何完整构建都写自己的 manifest,只挡 --limit 冒烟)。
   UI/API 两个入口都经 get_retriever,校验全覆盖;存量已回填主库+pc 库两份。
4. **/ready 同步探活阻塞事件循环** ✅:探活改 `run_in_threadpool` 包裹,3s 超时不再卡 loop。
5. **版本来源** ✅:单一来源仍是 `app/__init__.py::__version__`(0.2.0);Dockerfile 补
   ARG/LABEL org.opencontainers.image.version 并注释与 __version__ 同步;compose 保持 :latest 不掺和。

### 四次评审(验证层单项)→ ✅ 已修(2026-09-12,75 单测全绿 + 回落链路忠实演练)

- **默认 pytest 在受限环境仍挂**(scandir 被拒于 `Temp\pytest-of-...`):根因找到了——探针测的是
  temp **根**,而实际失败点在 `pytest-of-<user>` **子树**(常由早前另一安全上下文创建,ACL 坏)。
  修复:探针改为打在 pytest 原生默认根 `_pytest_default_root()`(temp/pytest-of-<user>)上,
  完整动作面(建/写/枚举/删);"根可写但子树不可枚举"不再误判放行。
- **回落目录轮转**:`.pytest_tmp → .pytest_tmp2 → .pytest_tmp3`,候选自身损坏(如被系统锁死)
  自动顺延,不被毒害;全灭则交还原生行为让 pytest 报自己的错。
- **验证**:本机忠实演练(把默认根硬指到文件路径=探测必败)下裸 `pytest` 75 全过、
  正确回落项目内并越过锁死目录。仍无法在本机复现评审沙箱本体,若其环境再挂,
  报错信息将指向首个连探针都过不去的动作,可进一步定位。
- **为什么不采纳"ini 硬编 basetemp"**:本机(真实开发机)实测 pytest 在 repo 内建的 basetemp
  会被系统锁死(现存 `.pytest_tmp` 无法删除),硬编后第二次运行起必挂——两边环境互补,
  条件回落是唯一同时满足两边的方案。

### P1 工程加固 —— 1~4/6 已被二次评审处理吸收,仅剩:

- extract_json:长度上限 + schema 白名单字段

### P2 评估增强(可选,部署前后均可)

- 指标拆分:按题型/章节/问题长度切 recall;p95/p99 延迟;fallback 率;引用精确率
- 回归集:固定 200 题,配置变更时自动跑对比(eval/run_eval 已具备,补一个 trigger 脚本)

### 明确不做(评审同此判断)

- rerank/rewrite 不再进主线,保持实验开关(v0.3 GPU 场景留档即可)

## Docker 侧备忘(评审建议;部署已于 2026-09-12 取消,此处留档备查)

- 镜像固定依赖版本(requirements 锁版本)、非 root 用户、HEALTHCHECK
- 构建阶段校验 chunks.jsonl 与 Chroma 一致性(条数/hash 抽样)
