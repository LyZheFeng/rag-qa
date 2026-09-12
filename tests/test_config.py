"""配置约束与索引 manifest 单测（全部离线）。

Settings 会读仓库根 .env，但 init kwargs 优先级高于 env 文件，可放心传非法值断言报错。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from pipeline.config import API_MAX_K, Settings
from pipeline.manifest import check_manifest, write_manifest


# ---------- Settings 约束 ----------


def test_invalid_retriever_rejected():
    with pytest.raises(Exception):
        Settings(retriever="bogus")


def test_hybrid_candidates_below_api_max_k_rejected():
    # 候选深度小于 API k 上限会融合出不足 k 条,启动即拦
    with pytest.raises(Exception):
        Settings(hybrid_candidates=API_MAX_K - 1)
    Settings(hybrid_candidates=API_MAX_K)  # 边界值放行


def test_rrf_k_must_be_positive():
    with pytest.raises(Exception):
        Settings(rrf_k=0)
    Settings(rrf_k=1)


def test_real_env_loads_cleanly():
    # 实际 .env(RETRIEVER=hybrid 等)应原样通过校验
    s = Settings()
    assert s.retriever in {"vector", "hybrid", "rerank", "rewrite", "parentchild"}


# ---------- manifest ----------


def _write_chunks(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_manifest_roundtrip_ok(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a", "b", "c"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=3)
    state, msg, m = check_manifest(tmp_path, chunks, collection="c1")
    assert state == "ok"
    assert m["chunk_count"] == 3


def test_manifest_detects_chunks_drift(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a", "b", "c"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=3)
    _write_chunks(chunks, ["a", "b"])  # 语料/切块更新了,索引没重建
    state, _, _ = check_manifest(tmp_path, chunks, collection="c1")
    assert state == "mismatch"


def test_manifest_detects_collection_mismatch(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=1)
    state, _, _ = check_manifest(tmp_path, chunks, collection="c2")
    assert state == "mismatch"


def test_manifest_missing_is_soft(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    state, _, m = check_manifest(tmp_path, chunks, collection="c1")
    assert state == "missing"  # 旧索引:警告放行,不拒启
    assert m == {}


# ---------- conftest 临时目录回落 ----------


def test_pick_basetemp_none_when_system_temp_writable(tmp_path, monkeypatch):
    import conftest

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert conftest._pick_basetemp() is None


def test_pick_basetemp_fallback_when_system_temp_unwritable(tmp_path, monkeypatch):
    import conftest

    ghost = tmp_path / "no-such-dir"
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(ghost))
    picked = conftest._pick_basetemp()
    assert picked is not None and picked.name == ".pytest_tmp"


def test_pytest_configure_sets_basetemp_only_on_fallback(tmp_path, monkeypatch):
    import conftest

    class FakeConfig:
        def __init__(self, basetemp=None):
            self.option = SimpleNamespace(basetemp=basetemp)

    monkeypatch.setattr(conftest, "_pick_basetemp", lambda: None)
    cfg = FakeConfig()
    conftest.pytest_configure(cfg)
    assert cfg.option.basetemp is None  # 系统临时目录可用时不干预

    monkeypatch.setattr(conftest, "_pick_basetemp", lambda: conftest.REPO_ROOT / ".pytest_probe")
    cfg = FakeConfig(basetemp="explicit")  # 显式传参优先
    conftest.pytest_configure(cfg)
    assert cfg.option.basetemp == "explicit"

    fallback_dir = tmp_path / "fb"  # 真实回落路径:应 mkdir 并写回 option
    monkeypatch.setattr(conftest, "_pick_basetemp", lambda: fallback_dir)
    cfg = FakeConfig()
    conftest.pytest_configure(cfg)
    assert cfg.option.basetemp == str(fallback_dir) and fallback_dir.is_dir()
