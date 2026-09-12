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

### P1 工程加固(1~2 天)

- Settings 校验:`retriever` 用 Literal 枚举,`hybrid_candidates`/`rrf_k` 加范围(gt/le),
  非法配置启动即失败
- /health 增强:LLM 连通性(轻量 ping)、索引 chunk 数、模型维度、retriever 类型
- RagService.ask 同步阻塞:FastAPI 侧改 `run_in_threadpool`(快)或异步客户端(重);
  加请求超时与简单并发信号量
- 索引版本管理:chunks.jsonl 与 Chroma collection 显式版本号(如 fastapi_zh_v2),
  BM25 文件与 collection 校验同源,防错配
- extract_json:长度上限 + schema 白名单字段

### P2 评估增强(可选,部署前后均可)

- 指标拆分:按题型/章节/问题长度切 recall;p95/p99 延迟;fallback 率;引用精确率
- 回归集:固定 200 题,配置变更时自动跑对比(eval/run_eval 已具备,补一个 trigger 脚本)

### 明确不做(评审同此判断)

- rerank/rewrite 不再进主线,保持实验开关(v0.3 GPU 场景留档即可)

## Docker 侧备忘(评审建议;部署已于 2026-09-12 取消,此处留档备查)

- 镜像固定依赖版本(requirements 锁版本)、非 root 用户、HEALTHCHECK
- 构建阶段校验 chunks.jsonl 与 Chroma 一致性(条数/hash 抽样)
