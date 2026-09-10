"""模型下载脚本。用法：
  python scripts/download_models.py --embed          # bge-m3（Phase 0）
  python scripts/download_models.py --rerank         # bge-reranker-v2-m3（Phase 4 前）
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from huggingface_hub import snapshot_download

MODELS = {
    "embed": "BAAI/bge-m3",
    "rerank": "BAAI/bge-reranker-v2-m3",
}


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    for arg in args:
        key = arg.lstrip("-")
        if key not in MODELS:
            print(f"未知参数 {arg}，可选: {list(MODELS)}")
            sys.exit(1)
        repo = MODELS[key]
        path = snapshot_download(repo)
        print(f"已就绪: {repo} -> {path}")


if __name__ == "__main__":
    main()
