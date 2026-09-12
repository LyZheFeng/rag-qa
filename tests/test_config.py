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
    state, msg, m = check_manifest(tmp_path, chunks, collection="c1", embed_model="m")
    assert state == "ok"
    assert m["chunk_count"] == 3
    assert (tmp_path / "manifest.c1.json").exists()  # 按 collection 分文件


def test_manifest_detects_chunks_drift(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a", "b", "c"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=3)
    _write_chunks(chunks, ["a", "b"])  # 语料/切块更新了,索引没重建
    state, _, _ = check_manifest(tmp_path, chunks, collection="c1", embed_model="m")
    assert state == "mismatch"


def test_manifest_detects_collection_mismatch(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=1)
    # 模拟错拷:manifest.c1.json 被复制成 manifest.c2.json,内容记的还是 c1
    (tmp_path / "manifest.c2.json").write_text(
        (tmp_path / "manifest.c1.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    state, _, _ = check_manifest(tmp_path, chunks, collection="c2", embed_model="m")
    assert state == "mismatch"


def test_manifest_detects_embed_model_mismatch(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="BAAI/bge-m3", chunk_count=1)
    state, msg, _ = check_manifest(tmp_path, chunks, collection="c1", embed_model="other/model")
    assert state == "mismatch"
    assert "嵌入模型" in msg


def test_manifest_per_collection_coexist(tmp_path):
    # 主库与 pc 库各绑各的,互不覆盖
    main = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    pc = _write_chunks(tmp_path / "chunks_pc.jsonl", ["b", "c"])
    write_manifest(tmp_path, main, collection="fastapi_zh_v1", embed_model="m", chunk_count=1)
    write_manifest(tmp_path, pc, collection="fastapi_zh_pc", embed_model="m", chunk_count=2)
    assert check_manifest(tmp_path, main, collection="fastapi_zh_v1", embed_model="m")[0] == "ok"
    assert check_manifest(tmp_path, pc, collection="fastapi_zh_pc", embed_model="m")[0] == "ok"


def test_manifest_missing_is_soft(tmp_path):
    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    state, _, m = check_manifest(tmp_path, chunks, collection="c1", embed_model="m")
    assert state == "missing"  # 旧索引:警告放行,不拒启
    assert m == {}


# ---------- retriever 层索引校验(_validate_index) ----------


def test_validate_index_mismatch_raises(tmp_path):
    from app import retriever as R

    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=1)
    _write_chunks(chunks, ["changed"])
    with pytest.raises(RuntimeError, match="索引版本校验失败"):
        R._validate_index(tmp_path, chunks, collection="c1", embed_model="m")


def test_validate_index_missing_warns_not_raises(tmp_path):
    from app import retriever as R

    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    R._validate_index(tmp_path, chunks, collection="c1", embed_model="m")  # 无 manifest:不抛


def test_validate_index_count_mismatch_raises(tmp_path, monkeypatch):
    from app import retriever as R

    chunks = _write_chunks(tmp_path / "chunks.jsonl", ["a"])
    write_manifest(tmp_path, chunks, collection="c1", embed_model="m", chunk_count=1)
    monkeypatch.setattr(R, "get_collection", lambda d, c: SimpleNamespace(count=lambda: 99))
    with pytest.raises(RuntimeError, match="条数"):
        R._validate_index(tmp_path, chunks, collection="c1", embed_model="m")
    # check_count=False(parentchild 的父块路径)时只做文件级校验,不碰 chroma
    monkeypatch.setattr(R, "get_collection", lambda d, c: (_ for _ in ()).throw(AssertionError("不应打开 chroma")))
    R._validate_index(tmp_path, chunks, collection="c1", embed_model="m", check_count=False)


# ---------- conftest 临时目录回落 ----------


def test_pick_basetemp_none_when_default_root_usable(tmp_path, monkeypatch):
    import conftest

    monkeypatch.setattr(conftest, "_pytest_default_root", lambda: tmp_path / "pytest-of-u")
    assert conftest._pick_basetemp() is None  # 原生子树可用 → 不干预


def test_pick_basetemp_falls_back_when_default_root_unusable(tmp_path, monkeypatch):
    import conftest

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    # 模拟"temp 下不可建/不可枚举":父路径是文件 → mkdir 必败
    monkeypatch.setattr(conftest, "_pytest_default_root", lambda: blocker / "pytest-of-u")
    monkeypatch.setattr(conftest, "REPO_ROOT", tmp_path)
    assert conftest._pick_basetemp() == tmp_path / ".pytest_tmp"


def test_pick_basetemp_rotates_past_poisoned_candidate(tmp_path, monkeypatch):
    import conftest

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(conftest, "_pytest_default_root", lambda: blocker / "pytest-of-u")
    monkeypatch.setattr(conftest, "REPO_ROOT", tmp_path)
    # 模拟候选目录被锁死/占用(名字被文件占住 → mkdir 必败),应顺延下一个候选
    (tmp_path / ".pytest_tmp").write_text("占位", encoding="utf-8")
    assert conftest._pick_basetemp() == tmp_path / ".pytest_tmp2"


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

    fallback_dir = tmp_path / "fb"
    fallback_dir.mkdir()  # 真实 _pick_basetemp 返回前经 _probe_candidate 已建好目录,如实模拟
    monkeypatch.setattr(conftest, "_pick_basetemp", lambda: fallback_dir)
    cfg = FakeConfig()
    conftest.pytest_configure(cfg)
    assert cfg.option.basetemp == str(fallback_dir)
