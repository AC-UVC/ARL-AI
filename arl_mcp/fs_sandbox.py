"""文件沙箱：MCP 的所有文件增删改查、临时文件只允许发生在工作目录内。

规则：
- 相对路径一律相对工作目录解析；
- 绝对路径 / 带盘符 / UNC 路径，realpath 归一化后必须仍落在工作目录内；
- ``..`` 穿越、软链接/目录联接逃逸、兄弟目录前缀混淆（如 ``ARL-AI-evil``）全部拒绝；
- 临时文件唯一去处：``<工作目录>/.tmp/``。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import config


class SandboxError(PermissionError):
    """试图越过工作目录边界时抛出。"""


_root: Path | None = None


def set_workspace(path: str | Path) -> Path:
    """设置（测试/运行时）沙箱根目录。"""
    global _root
    _root = Path(path).resolve()
    _root.mkdir(parents=True, exist_ok=True)
    return _root


def root() -> Path:
    if _root is None:
        set_workspace(config.workspace_root())
    return _root


def tmp_root() -> Path:
    p = root() / ".tmp"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_inside(p: Path) -> bool:
    try:
        p.relative_to(root())
        return True
    except ValueError:
        return False


def resolve_safe(user_path: str | Path, *, base: Path | None = None,
                 must_exist: bool = False) -> Path:
    """把用户给的路径解析为工作目录内的绝对路径，越界即拒绝。"""
    if user_path is None or str(user_path).strip() == "" or "\x00" in str(user_path):
        raise SandboxError("非法路径：为空或包含空字节")

    raw = Path(str(user_path))
    if raw.drive or raw.root:  # 绝对路径 / 盘符 / UNC
        candidate = raw
    else:
        candidate = (base or root()) / raw

    # realpath 归一化：展开 ..、解析符号链接与目录联接
    resolved = Path(os.path.realpath(candidate))
    if not _is_inside(resolved):
        raise SandboxError(
            f"拒绝访问工作目录之外的路径（沙箱根: {root()}）: {user_path}")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


# ---------------------------------------------------------------- 增删改查

def fs_read(user_path: str, *, max_bytes: int = 2_000_000) -> str:
    p = resolve_safe(user_path, must_exist=True)
    if not p.is_file():
        raise IsADirectoryError(str(p))
    data = p.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def fs_write(user_path: str, content: str | bytes, *, append: bool = False) -> Path:
    p = resolve_safe(user_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    data = content.encode("utf-8") if isinstance(content, str) else content
    with open(p, mode) as f:
        f.write(data)
    return p


def fs_mkdir(user_path: str) -> Path:
    p = resolve_safe(user_path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def fs_delete(user_path: str) -> str:
    p = resolve_safe(user_path, must_exist=True)
    if p in (root(), tmp_root()):
        raise SandboxError("拒绝删除沙箱根目录 / .tmp 根目录")
    if p.is_dir():
        shutil.rmtree(p)
        return f"已删除目录: {p}"
    p.unlink()
    return f"已删除文件: {p}"


def fs_list(user_path: str = ".") -> list[dict]:
    p = resolve_safe(user_path, must_exist=True)
    if p.is_file():
        return [{"name": p.name, "type": "file", "size": p.stat().st_size,
                 "path": str(p)}]
    out = []
    for child in sorted(p.iterdir()):
        out.append({
            "name": child.name,
            "type": "dir" if child.is_dir() else "file",
            "size": child.stat().st_size if child.is_file() else None,
            "path": str(child),
        })
    return out


# ---------------------------------------------------------------- 临时文件

def temp_file(suffix: str = "", prefix: str = "arl-mcp-") -> Path:
    """临时文件唯一合法去处：<工作目录>/.tmp/。"""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=tmp_root())
    os.close(fd)
    return Path(path)


def temp_dir(prefix: str = "arl-mcp-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir=tmp_root()))


def clean_tmp() -> int:
    """清空 .tmp 下所有临时内容，返回清理条目数。"""
    n = 0
    for child in tmp_root().iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                continue
        n += 1
    return n
