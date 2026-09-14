"""测试专用 server 入口:真 app.mcp_server、假 retriever,走真实 stdio。

供 test_protocol_smoke_without_index 使用:CI 无嵌入模型/无索引也能跑通
协议面(search/资源/提示词/参数校验/异常脱敏)。query 含 "boom" 模拟基础
设施故障(OSError),含 "weird" 模拟第三方 SDK 自定义异常,含 "leak" 模拟
依赖库抛出的带内部细节的普通 RuntimeError。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.mcp_server as srv  # noqa: E402


class _SdkQuirk(Exception):
    """模拟第三方 SDK 抛出的自定义异常(不在任何已知白名单里)。"""


class FakeRetriever:
    """确定性命中,不加载模型;k 条带编号的假结果。"""

    def retrieve(self, query, k):
        if "boom" in query:
            raise OSError(r"C:\fake\model.bin 加载失败")
        if "weird" in query:
            raise _SdkQuirk("internal detail xyz")
        if "leak" in query:
            raise RuntimeError(r"connect http://10.0.0.1:8080 C:\secrets\llm.env")
        from app.schemas import Hit

        return [
            Hit(
                index=i + 1,
                chunk_id=f"fakedoc#{i:04d}",
                doc_name="fake.md",
                section_path=f"sec/{i}",
                text=f"命中:{query}(假结果 {i + 1})",
                score=round(0.9 - i / 10, 4),
            )
            for i in range(k)
        ]


srv._get_retriever = lambda: FakeRetriever()

if __name__ == "__main__":
    srv.main()
