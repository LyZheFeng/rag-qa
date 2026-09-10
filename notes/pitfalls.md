# 踩坑笔记（问题 → 尝试 → 结论，每条 3 行）

## 2026-09-10 · GitHub clone 断连

git clone github.com 443 全部超时（3 连败）→ 改 curl 拉 codeload.github.com 的 tar.gz 一次成功。
**结论：git 协议和 codeload 走的通道不同，clone 失败先试 `https://codeload.github.com/<org>/<repo>/tar.gz/refs/heads/<branch>`。**

## 2026-09-10 · bash 重试循环管道假成功

`cmd | tail -1 && break` 里管道让退出码变成 tail 的（恒为 0），失败也 break → 改为检查产物目录是否存在再 break。
**结论：Git Bash 写重试逻辑必须验证产物，不能信管道退出码。**

## 2026-09-10 · FastAPI 文档代码是构建期占位符

md 正文里 `{* ../../docs_src/xxx.py hl[4] *}` 不是代码，真实代码在仓库 docs_src/ 下（461 个 py）。
**结论：语料抓取要连同 docs_src 一起入库，loader 阶段把占位符替换为真实代码块；440 个占位符仅 1 个指向外部源码（fastapi/openapi/docs.py），保留为文字引用。**

## 2026-09-10 · 本机 grep 是 ugrep 别名，统计口径错乱

`grep '////'` 把 pattern 当选项解析报错；`\|` 行为与 GNU grep 不同导致"每行都匹配"的假统计（首次统计 tab 语法得 581/篇）。
**结论：本机做文本统计一律用 Python `re`，不信任 grep 别名；若用须加 `-e` 显式传 pattern。**

## 2026-09-10 · docs_src 占位符语法比预期丰富，严格正则漏 17 处

按 Phase 0 记录只写了 `hl[n]`，实际还有多区间行号 `ln[1:9,29:35]`、`hl[23:26]`、`title["..."]`，首版正则漏配 17 处占位符原样留在了 chunk 里。
**结论：占位符按 `ln[\d:, -]+` 宽匹配 + 多区间行选择实现；对照原 grep 总数 440 校验（439 解析 + 1 外部引用 = 440）闭环。**

## 2026-09-10 · base64 图片字面量撑爆 chunk 上限

stream-data.md 代码块内嵌 base64 PNG（单行 4269 字符），行切分无法拆、chunk 4269 字符超限。
**结论：cleaner 末段对 >1000 字符的行统一截断（占位符替换注入的内容也会流经这里），截断后全库 max=512。**

## 2026-09-10 · SentenceTransformer 离线加载要求 HF_HOME 在 import 前生效

embed.py 设了 HF_HUB_OFFLINE=1 但没设 HF_HOME，直接 import 的脚本找不到 D 盘缓存而报 LocalEntryNotFoundException（build_index.py 能跑、单写脚本不能）。
**结论：`pipeline/__init__.py` 导入即应用 .env 的 HF_HOME，保证任何入口先有缓存路径再 import transformers。**

## 2026-09-10 · pydantic v2 list[int] 把 JSON true 强转成 1

引用校验的 `isinstance(c, bool)` 排除写在 AnswerSpec 构造之后，模型输出 `citations: [true]` 被强转成 1 混过校验（单测抓到）。
**结论：对 LLM 输出的清洗必须先在原始 dict 上做，再交给 pydantic——强转会消灭类型证据。**


## rank-bm25 0.2.2 + NumPy 2.x 静默返回全 0 分(2026-09-10,Phase 4)

问题:`BM25Okapi.get_scores()` 对明显命中的词返回全 0,检索结果为空
尝试:最小复现确认是库与 NumPy 2.x 的兼容 bug,非调用方式问题
结论:自实现 Okapi BM25(app/hybrid.py,30 行倒排表),requirements 注明弃用;第三方"标准库"也要冒烟验证再信

## HF_HOME 不生效,模型下到 C 盘 2.1GB(2026-09-10,Phase 4)

问题:直接 import sentence_transformers/huggingface_hub 的脚本(模型验证、download_models.py)没先加载 pipeline.config,HF_HOME 落空,模型下到 C 盘默认 ~/.cache
尝试:事后 robocopy /MOVE 搬到 D 盘(注意 Git Bash 会把 robocopy 的 /E /MOVE 吃成路径,须经 PowerShell 调用)
结论:任何动 HF 的脚本,第一行必须 import pipeline.config(或显式设 HF_HOME);download_models.py 已修
