"""MCP 工具层测试：直接调用工具函数（FastMCP 装饰器返回原函数）。"""

import json

import pytest

from arl_mcp import server
from arl_mcp.arl_client import set_client
from arl_mcp.fs_sandbox import set_workspace


class FakeClient:
    """模拟 ARLClient，只实现工具层用到的接口。"""

    def __init__(self):
        self.exported = None

    def request(self, method, path, params=None, json_body=None):
        return {"code": 200, "data": {"echo": path}}

    def query(self, collection, page=1, size=20, order=None, filters=None):
        return {"page": page, "size": size, "total": 42,
                "items": [{"collection": collection, "filters": filters or {}}]}

    def list_tasks(self, page=1, size=20, order=None, **filters):
        return {"page": page, "size": size, "total": 1,
                "items": [{"status": "done", **filters}]}

    def create_task(self, name, target, options):
        return [{"task_id": "abc123", "status": "waiting",
                 "options": options}]

    def get_task(self, task_id):
        return {"_id": task_id, "status": "done"}

    def stop_task(self, task_id):
        return {"code": 200}

    def delete_tasks(self, task_ids, del_task_data=False):
        return {"code": 200}

    def restart_tasks(self, task_ids):
        return {"code": 200}

    def delete_assets(self, collection, ids):
        return {"code": 200, "deleted": len(ids)}

    def export_task(self, task_id):
        self.exported = task_id
        return b"XLSXDATA"


@pytest.fixture(autouse=True)
def _env(tmp_path):
    set_workspace(tmp_path)
    set_client(FakeClient())
    yield
    set_client(None)


def _loads(s):
    return json.loads(s)


def test_fs_tools_roundtrip():
    server.fs_write("报告/x.md", "# hi")
    assert server.fs_read("报告/x.md") == "# hi"
    entries = _loads(server.fs_list("."))
    assert any(e["name"] == "报告" for e in entries)


def test_fs_tools_reject_escape():
    with pytest.raises(Exception):
        server.fs_write("../x", "y")


def test_arl_create_task_tool():
    out = _loads(server.arl_create_task("n", "example.com",
                                        nuclei_scan=True))
    assert out["items"][0]["task_id"] == "abc123"
    assert out["items"][0]["options"]["nuclei_scan"] is True


def test_arl_query_site_merges_task_id():
    out = _loads(server.arl_query_sites(task_id="t1",
                                        filters={"title": "login"}))
    assert out["total"] == 42
    assert out["items"][0]["filters"] == {"task_id": "t1", "title": "login"}


def test_arl_export_task_saves_in_workspace():
    out = _loads(server.arl_export_task("t9"))
    assert out["path"].endswith("ARL报告_t9.xlsx")
    with open(out["path"], "rb") as f:
        assert f.read() == b"XLSXDATA"


def test_arl_api_call_rejects_bad_method():
    out = _loads(server.arl_api_call("TRACE", "/api/task/"))
    assert "error" in out


def test_fetch_url_blocks_private_before_request(monkeypatch):
    called = {"n": 0}

    def fake_get(*a, **kw):
        called["n"] += 1
        raise AssertionError("内网 URL 不应发起请求")

    monkeypatch.setattr(server.httpx, "get", fake_get)
    out = _loads(server.fetch_url("http://192.168.1.1/x"))
    assert "error" in out and called["n"] == 0
    out = _loads(server.fetch_url("http://localhost/"))
    assert "error" in out and called["n"] == 0
