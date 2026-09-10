#!/usr/bin/env bash
# Phase 0 环境安装：venv → 依赖 → bge-m3 下载（日志 data/cache/setup.log）
set -e
cd "$(dirname "$0")/.."

echo "=== [1/3] 创建 venv ==="
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip -q

echo "=== [2/3] 安装依赖（torch CPU 较大，耐心） ==="
.venv/Scripts/pip install -r requirements.txt

echo "=== [3/3] 下载 bge-m3（hf-mirror） ==="
export HF_HOME="$(pwd)/data/cache/hf"
export HF_ENDPOINT=https://hf-mirror.com
.venv/Scripts/python scripts/download_models.py --embed

echo "=== setup 完成 ==="
