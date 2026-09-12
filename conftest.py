"""仓库根 conftest：临时目录策略。

默认用系统临时目录（pytest 原生行为）。受限环境（某些 CI 沙箱的系统 temp 不可写）
会导致 tmp_path 系 fixture 全军覆没，这里在启动时探测一次：不可写才回落到仓库内
.pytest_tmp（已 gitignore）。--basetemp 显式传参时不干预。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _is_writable_dir(path: Path) -> bool:
    """真探针：os.access 在 Windows 上不可靠，实际建删一次。"""
    try:
        probe = path / ".rag-qa-write-probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _pick_basetemp() -> Path | None:
    """系统临时目录可写 → None（保持 pytest 默认）；不可写 → 仓库内回落路径。"""
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
