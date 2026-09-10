"""模型下载脚本。用法：
  python scripts/download_models.py --embed          # bge-m3（Phase 0）
  python scripts/download_models.py --rerank         # bge-reranker-v2-m3（Phase 4 前）

HF_HOME/HF_ENDPOINT 从仓库根 .env 读取（默认 D 盘缓存 + hf-mirror），
必须在 import huggingface_hub 之前生效。
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.config import get_settings  # noqa: E402  (import 即应用 .env 的 HF_HOME/HF_ENDPOINT)

get_settings()
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from huggingface_hub import snapshot_download  # noqa: E402

MODELS = {
    "embed": "BAAI/bge-m3",
    "rerank": "BAAI/bge-reranker-v2-m3",
}


def main():
    args = sys.argv[1:]
    if not args or any(a.lstrip("-") not in MODELS for a in args):
        print(__doc__)
        print(f"缓存位置 HF_HOME={os.environ.get('HF_HOME', '(默认 C 盘 ~/.cache)')}")
        sys.exit(1)
    for arg in args:
        repo = MODELS[arg.lstrip("-")]
        path = snapshot_download(repo)
        print(f"已就绪: {repo} -> {path}")


if __name__ == "__main__":
    main()
