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
