"""索引 manifest：构建侧写入，服务侧启动校验。

每个 collection 一份 manifest（manifest.{collection}.json），绑定同一次构建的
四件事：Chroma collection、chunks jsonl、嵌入模型、条数。语料/切块/模型更新但
只重建了其中一个索引时（BM25 读 jsonl、向量读 Chroma），哈希/模型/条数对不上
即拒绝启动，防隐蔽的版本错配。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

# 校验状态：ok=一致 / missing=无 manifest（旧索引，警告放行）/ mismatch=版本错配（拒绝启动）
ManifestState = str


class IndexValidationError(RuntimeError):
    """manifest 绑定校验失败（mismatch）。

    消息是面向最终用户的诊断（哪个文件、什么不一致、怎么修），允许完整回传
    客户端；区别于依赖库可能抛出的普通 RuntimeError——后者可能含内部路径/
    配置/地址，边界层（如 MCP ToolError）应脱敏。继承 RuntimeError 以兼容
    既有的捕获与测试断言。
    """


def manifest_path(chroma_dir: Path, collection: str) -> Path:
    return chroma_dir / f"manifest.{collection}.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_manifest(
    chroma_dir: Path,
    chunks_path: Path,
    *,
    collection: str,
    embed_model: str,
    chunk_count: int,
) -> Path:
    payload = {
        "collection": collection,
        "chunks_file": chunks_path.name,
        "chunks_sha256": _sha256(chunks_path),
        "chunk_count": chunk_count,
        "embed_model": embed_model,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    path = manifest_path(chroma_dir, collection)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def check_manifest(
    chroma_dir: Path, chunks_path: Path, *, collection: str, embed_model: str
) -> tuple[ManifestState, str, dict]:
    """文件级校验（不打开 Chroma）。返回 (状态, 人读说明, manifest 原文)。

    条数比对由调用方拿着 manifest["chunk_count"] 对 collection.count() 做。
    """
    path = manifest_path(chroma_dir, collection)
    if not path.exists():
        return "missing", f"索引 manifest 不存在（{path}），旧索引建议重跑 build_index 生成", {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return "mismatch", f"manifest 损坏：{e}", {}
    if manifest.get("collection") != collection:
        return (
            "mismatch",
            f"manifest 记录 collection={manifest.get('collection')!r}，与实际 {collection!r} 不一致",
            manifest,
        )
    if manifest.get("embed_model") != embed_model:
        return (
            "mismatch",
            f"manifest 记录 embed_model={manifest.get('embed_model')!r}，当前 {embed_model!r}"
            "（更换嵌入模型必须重建索引，向量不可混用）",
            manifest,
        )
    if not chunks_path.exists():
        return "mismatch", f"chunks 文件缺失：{chunks_path}", manifest
    if _sha256(chunks_path) != manifest.get("chunks_sha256"):
        return "mismatch", f"{chunks_path.name} 与 manifest 哈希不一致（单侧重建过索引）", manifest
    return "ok", f"{manifest.get('chunk_count')} chunks", manifest
