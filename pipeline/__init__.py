# Phase 1 数据管道：loader → cleaner → chunker → embed → chroma
# 导入即应用 .env 中的 HF_HOME 等环境变量（须在 transformers/sentence_transformers 之前）
from .config import get_settings

get_settings()
