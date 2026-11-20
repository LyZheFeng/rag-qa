"""HTTP 冒烟:真起一个 uvicorn 进程,确认"部署形态能启动"。

为什么单测不够:测试用 FastAPI TestClient 走进程内 ASGI 调用,不经过 uvicorn、
不监听端口,也不校验启动期配置——"pytest 全绿"证明不了这台机器上
`uvicorn app.api:app` 能起来。CI(ubuntu)跑一遍本脚本,补上这一层。

**`--lifespan off` 是刻意的**:完整启动会加载 bge-m3 嵌入模型并校验索引 manifest,
CI 里既没有 `data/chroma/` 也没有模型缓存(离线、几个 GB),跑不起来。关掉 lifespan 后
仍然验证到:依赖导入(torch/chromadb 等)、路由注册、端口监听、HTTP 栈能把 openapi 返回 ——
也就是"装得上、起得来"这一层;lifespan 的索引校验由单测(test_config/test_service_retry)覆盖。

不依赖 LLM、不依赖索引,离线可跑。用法:`python -X utf8 scripts/smoke_http.py`,失败退出码 1。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PATHS = {"/health", "/ready", "/ask", "/ask/stream"}


def _free_port() -> int:
    """让系统分配空闲端口,避免 CI 并发/本机占用导致的偶发失败。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _fetch_openapi(port: int, deadline: float) -> dict:
    """轮询 /openapi.json 直到超时;启动期连不上属正常,一直连不上才算失败。"""
    url = f"http://127.0.0.1:{port}/openapi.json"
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                assert resp.status == 200, f"/openapi.json 状态码 {resp.status}"
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            last = e
            time.sleep(0.2)
    raise RuntimeError(f"{url} 在超时前未就绪:{last}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=60.0, help="等待服务就绪的秒数(首次导入 torch 较慢)")
    args = ap.parse_args(argv)

    port = _free_port()
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        # 启动阶段不碰真实模型/LLM;测试值只为让 Settings 能实例化
        "LLM_API_KEY": os.environ.get("LLM_API_KEY", "test"),
        "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", "http://test.local/v1"),
    }
    cmd = [
        sys.executable, "-m", "uvicorn", "app.api:app",
        "--host", "127.0.0.1", "--port", str(port),
        "--lifespan", "off", "--log-level", "warning",
    ]

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            spec = _fetch_openapi(port, time.monotonic() + args.timeout)
            paths = set(spec.get("paths", {}))
            missing = EXPECTED_PATHS - paths
            assert not missing, f"/openapi.json 缺路由:{sorted(missing)}"
            print(f"ok: uvicorn 启动并返回 openapi,路由 {sorted(EXPECTED_PATHS)} 齐全")
            return 0
        except Exception as e:  # noqa: BLE001 - 冒烟脚本:任何异常都要带服务日志失败退出
            proc.poll()
            log.seek(0)
            tail = log.read()[-3000:]
            print(f"FAIL: {e}\n--- uvicorn 输出 ---\n{tail}", file=sys.stderr)
            return 1
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())