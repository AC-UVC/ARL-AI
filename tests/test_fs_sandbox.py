"""文件沙箱测试：所有临时文件（含 pytest 自身）都必须落在工作目录内。"""

import sys

import pytest

from arl_mcp import fs_sandbox
from arl_mcp.fs_sandbox import (SandboxError, clean_tmp, fs_delete, fs_list,
                                fs_mkdir, fs_read, fs_write, resolve_safe,
                                set_workspace, temp_dir, temp_file)


@pytest.fixture(autouse=True)
def _ws(tmp_path):
    set_workspace(tmp_path)


def test_roundtrip_inside_workspace():
    fs_write("报告/任务A.md", "# 内容")
    assert fs_read("报告/任务A.md") == "# 内容"


def test_traversal_rejected():
    with pytest.raises(SandboxError):
        fs_write("../逃逸.txt", "x")
    with pytest.raises(SandboxError):
        resolve_safe("../../etc/passwd")
    with pytest.raises(SandboxError):
        fs_read("a/../../x")


def test_absolute_outside_rejected():
    with pytest.raises(SandboxError):
        fs_write(r"C:\Windows\System32\evil.txt", "x")
    with pytest.raises(SandboxError):
        fs_read(r"C:\Users\secret.txt")


def test_sibling_prefix_confusion_rejected(tmp_path):
    # 沙箱根是 tmp_path，试图写它的兄弟目录 ARL-AI-evil：前缀相似但不在根内
    sibling = tmp_path.parent / (tmp_path.name + "-evil") / "x.txt"
    with pytest.raises(SandboxError):
        fs_write(str(sibling), "x")


def test_temp_files_only_in_tmp_root():
    f = temp_file(suffix=".json")
    d = temp_dir()
    assert f.parent.name == ".tmp" and f.exists()
    assert d.parent.name == ".tmp" and d.is_dir()


def test_delete_refuses_roots():
    with pytest.raises(SandboxError):
        fs_delete(".")
    with pytest.raises(SandboxError):
        fs_delete(".tmp")


def test_delete_dir_recursive():
    fs_write("d/a.txt", "1")
    fs_write("d/sub/b.txt", "2")
    out = fs_delete("d")
    assert "已删除目录" in out and not (fs_sandbox.root() / "d").exists()


def test_mkdir_and_list():
    fs_mkdir("资产")
    fs_write("资产/a.txt", "x")
    entries = fs_list(".")
    names = {e["name"] for e in entries}
    assert "资产" in names and fs_sandbox.tmp_root().name == ".tmp"


def test_clean_tmp_counts():
    temp_file()
    temp_file()
    temp_dir()
    assert clean_tmp() == 3
    assert clean_tmp() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 大小写不敏感")
def test_case_insensitive_path_stays_inside():
    fs_write("hello.txt", "ok")
    assert fs_read("HELLO.TXT") == "ok"
