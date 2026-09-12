"""仓库根 conftest：临时目录策略。

默认用系统临时目录（pytest 原生行为）。受限环境（某些 CI 沙箱）的系统 temp 可能
"能建文件但不能枚举/删除目录"，会让 tmp_path 系 fixture 全军覆没；这里在启动时
做一次完整动作面探测（建子目录 → 写文件 → scandir 枚举 → 删文件 → 删子目录），
任何一步被拒就回落到仓库内 .pytest_tmp（已 gitignore）。
--basetemp 显式传参时不干预。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _is_writable_dir(path: Path) -> bool:
    """完整动作面探针：os.access 在 Windows 上不可靠，只测建文件会漏掉
    "可建不可枚举"的受限沙箱（pytest 的 tmp_path 还要 scandir/rmdir）。"""
    sub = path / ".rag-qa-probe-dir"
    probe = sub / ".rag-qa-write-probe"
    try:
        sub.mkdir(exist_ok=True)
        probe.write_text("x", encoding="utf-8")
        next(iter(os.scandir(sub)), None)  # 枚举权限
        probe.unlink()
        sub.rmdir()
        return True
    except OSError:
        return False
    finally:  # 失败路径上尽力清理探针
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            sub.rmdir()
        except OSError:
            pass


def _pick_basetemp() -> Path | None:
    """系统临时目录可用 → None（保持 pytest 默认）；不可用 → 仓库内回落路径。"""
    root = Path(tempfile.gettempdir())
    if not root.exists() or not _is_writable_dir(root):
        return REPO_ROOT / ".pytest_tmp"
    return None


def pytest_configure(config):
    if config.option.basetemp:
        return  # 显式传参优先
    fallback = _pick_basetemp()
    if fallback is not None:
        fallback.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(fallback)
