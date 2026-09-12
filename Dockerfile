# FastAPI 中文文档 RAG(v0.2-hybrid 运行时)
# 镜像含代码+Chroma 检索库+BM25 语料;bge-m3 模型首次启动时下载到 hf-cache 卷(hf-mirror)
FROM python:3.13-slim

# 镜像版本与 app/__init__.py 的 __version__ 保持同步(单一来源在后者,改版本两处同改)
ARG APP_VERSION=0.2.0
LABEL org.opencontainers.image.title="rag-qa" \
      org.opencontainers.image.version=${APP_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    HF_ENDPOINT=https://hf-mirror.com \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/rag-qa

# torch 先装 CPU 版(Linux 下默认源会拖 CUDA 依赖 ~2.5GB)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN grep -v '^#' requirements.txt | grep -v '^-e' | xargs -r pip install

COPY app/ app/
COPY pipeline/ pipeline/
COPY data/chroma/ data/chroma/
COPY data/chunks/chunks.jsonl data/chunks/

EXPOSE 8000 8501
