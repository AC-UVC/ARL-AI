"""ARL API 客户端测试（httpx.MockTransport，不打真实网络）。"""

import httpx
import pytest

from arl_mcp.arl_client import ARLApiError, ARLClient


def make_client(handler, **kw) -> ARLClient:
    return ARLClient(base_url="https://arl.test", username="admin",
                     password="pw",
                     transport=httpx.MockTransport(handler), **kw)


def ok(body):
    return httpx.Response(200, json=body)


def test_login_then_token_header():
    seen = {}

    def handler(req):
        if req.url.path == "/api/user/login":
            assert req.read()
            return ok({"code": 200, "data": {"token": "T1"}})
        seen["token"] = req.headers.get("Token")
        return ok({"code": 200, "items": [], "total": 0})

    c = make_client(handler)
    c.request("GET", "/api/task/")
    assert seen["token"] == "T1"


def test_relogin_on_401_once():
    logins = {"n": 0}

    def handler(req):
        if req.url.path == "/api/user/login":
            logins["n"] += 1
            return ok({"code": 200, "data": {"token": f"T{logins['n']}"}})
        if req.headers.get("Token") != "T1":
            return ok({"code": 401, "message": "not login"})
        return ok({"code": 200, "items": ["fine"]})

    c = make_client(handler)
    data = c.request("GET", "/api/task/")
    assert data["items"] == ["fine"]
    assert logins["n"] == 1


def test_static_token_never_relogin():
    def handler(req):
        if req.url.path == "/api/user/login":
            raise AssertionError("静态 Token 模式不应登录")
        return ok({"code": 401, "message": "not login"})

    c = make_client(handler, token="STATIC")
    with pytest.raises(ARLApiError) as e:
        c.request("GET", "/api/task/")
    assert e.value.code == 401


def test_api_code_not_200_raises():
    def handler(req):
        return ok({"code": 104, "message": "任务运行中,不能删除", "data": {}})

    c = make_client(handler)
    with pytest.raises(ARLApiError) as e:
        c.delete_tasks(["x"])
    assert e.value.code == 104 and "任务运行中" in e.value.message


def test_create_task_flat_body():
    captured = {}

    def handler(req):
        if req.url.path == "/api/user/login":
            return ok({"code": 200, "data": {"token": "T"}})
        captured["body"] = req.read()
        return ok({"code": 200, "items": [{"task_id": "abc", "status": "waiting"}]})

    c = make_client(handler)
    items = c.create_task("test", "example.com",
                          {"port_scan": True, "port_scan_type": "top100"})
    assert items[0]["task_id"] == "abc"
    import json
    body = json.loads(captured["body"])
    # 扁平结构：开关在顶层，没有嵌套 task_data
    assert body["name"] == "test" and body["target"] == "example.com"
    assert body["port_scan_type"] == "top100" and "task_data" not in body


def test_query_collection_whitelist():
    c = make_client(lambda req: ok({"code": 200}))
    with pytest.raises(ARLApiError):
        c.query("user")        # 用户集合不允许通过查询口拿
    with pytest.raises(ARLApiError):
        c.query("../../evil")


def test_delete_assets_whitelist():
    def handler(req):
        if req.url.path == "/api/user/login":
            return ok({"code": 200, "data": {"token": "T"}})
        return ok({"code": 200})

    c = make_client(handler)
    with pytest.raises(ARLApiError):
        c.delete_assets("user", ["1"])
    c.delete_assets("site", ["1", "2"])  # 白名单内放行


def test_api_path_must_start_with_api():
    c = make_client(lambda req: ok({"code": 200}))
    with pytest.raises(ARLApiError):
        c.request("GET", "/user/login")


def test_export_task_raw_bytes():
    def handler(req):
        if req.url.path == "/api/user/login":
            return ok({"code": 200, "data": {"token": "T"}})
        assert req.url.path == "/api/export/t1"
        return httpx.Response(200, content=b"XLSXBYTES")

    c = make_client(handler)
    assert c.export_task("t1") == b"XLSXBYTES"


def test_bad_arl_url_rejected():
    with pytest.raises(ValueError):
        ARLClient(base_url="file://x", token="t")
