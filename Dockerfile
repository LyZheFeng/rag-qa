# FastAPI 中文文档 RAG(v0.2-hybrid 运行时)
# 镜像含代码+Chroma 检索库+BM25 语料;bge-m3 模型首次启动时下载到 hf-cache 卷(hf-mirror)
FROM python:3.13-slim

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
