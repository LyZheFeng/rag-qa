"""仓库根 conftest：临时目录策略。

默认用 pytest 原生行为（系统临时目录下的 pytest-of-<user> 子树）。受限沙箱里
观测到的故障点是：temp 根可写，但 pytest-of-<user> 子树（常由先前另一个安全
上下文创建）不可枚举/不可写——所以探针必须打在 pytest 实际会用的那棵子树上，
而不是 temp 根（测 temp 根会误判放行）。

探测失败才回落项目内（.pytest_tmp*，已 gitignore）；候选目录若自身已损坏
（不可探测）则顺延下一个，避免被锁死目录毒害后续所有运行。
--basetemp 显式传参时不干预。
"""

from __future__ import annotations

import getpass
import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
_FALLBACK_NAMES = (".pytest_tmp", ".pytest_tmp2", ".pytest_tmp3")


def _is_writable_dir(path: Path) -> bool:
    """完整动作面探针：建子目录 → 写文件 → scandir 枚举 → 删文件 → 删子目录。
    os.access 在 Windows 上不可靠；只测建文件会漏掉"可建不可枚举"的受限沙箱。"""
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


def _pytest_default_root() -> Path:
    """镜像 pytest 原生默认 basetemp 根：temp/pytest-of-<user>（探测目标）。"""
    try:
        user = getpass.getuser()
    except (ImportError, KeyError):
        user = "unknown"
    return Path(tempfile.gettempdir()) / f"pytest-of-{user}"


def _probe_candidate(c: Path) -> bool:
    try:
        c.mkdir(parents=True, exist_ok=True)
    except OSError:  # 父路径是文件/ACL 拒绝建目录等
        return False
    return _is_writable_dir(c)


def _pick_basetemp() -> Path | None:
    """pytest 默认子树可用 → None（保持原生行为）；否则给一个可用的项目内路径。"""
    if _probe_candidate(_pytest_default_root()):
        return None
    for name in _FALLBACK_NAMES:
        cand = REPO_ROOT / name
        if _probe_candidate(cand):
            return cand
    return None  # 候选全灭：交还原生行为，让 pytest 报它自己的错（比静默猜测好）


def pytest_configure(config):
    if config.option.basetemp:
        return  # 显式传参优先
    fallback = _pick_basetemp()
    if fallback is not None:
        config.option.basetemp = str(fallback)
