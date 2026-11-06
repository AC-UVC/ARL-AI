"""ARL REST API 客户端。

要点（与 ARL 源码 app/routes/ 对齐）：
- 登录: POST /api/user/login {username, password} -> data.token；
- 后续请求 header 为 ``Token: <token>``（裸 token，无 Bearer）；
- 所有响应 HTTP 状态恒为 200，成功与否看 body 的 ``code`` 字段（200 才成功）；
- 任务创建 body 是扁平结构（开关直接在顶层，不是嵌套 task_data）；
- 任务删除/批量停止/重启是 POST，停止单个任务是 GET /api/task/stop/<id>。
"""

from __future__ import annotations

import threading

import httpx

from . import config
from .url_guard import UrlBlocked, validate_url

# 允许查询/操作的集合白名单（app/routes 下真实存在的列表路由）
LIST_COLLECTIONS = {
    "task", "site", "domain", "ip", "url", "cert", "service", "fileleak",
    "cip", "wih", "npoc_service", "nuclei_result", "vuln", "poc",
    "fingerprint", "stat_finger", "asset_scope", "asset_site", "asset_domain",
    "asset_ip", "asset_wih", "scheduler", "task_schedule",
    "github_task", "github_result", "github_monitor_result",
}

# 支持按 _id 列表删除的集合（POST /api/<coll>/delete/ body {"_id":[...]}）
DELETABLE_COLLECTIONS = {
    "site", "domain", "ip", "url", "cert", "fileleak", "wih",
    "nuclei_result", "vuln",
}

HTTP_METHODS = {"GET", "POST", "PUT", "DELETE"}


class ARLApiError(RuntimeError):
    """ARL 返回 code != 200 或通信失败。"""

    def __init__(self, code, message: str, data=None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"ARL 错误 code={code}: {message}")


class ARLClient:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 username: str | None = None, password: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = (base_url or config.ARL_URL).rstrip("/")
        if config.ARL_STRICT_URL_GUARD:
            # 严格模式：ARL 地址也走完整 SSRF 校验（拒绝内网/环回）
            try:
                validate_url(self.base_url)
            except UrlBlocked as e:
                raise ValueError(f"ARL_URL 不合法: {e}") from e
        else:
            # 默认：ARL 地址是运维部署的可信上游（通常为本机/内网），
            # 只校验协议；出网防护管的是工具参数里的用户 URL。
            from urllib.parse import urlparse
            if urlparse(self.base_url).scheme not in ("http", "https"):
                raise ValueError(f"ARL_URL 仅允许 http/https: {self.base_url}")

        self._static_token = config.ARL_TOKEN if token is None else token
        self._token = self._static_token
        self._username = config.ARL_USER if username is None else username
        self._password = config.ARL_PASS if password is None else password
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=config.ARL_TIMEOUT,
            verify=config.ARL_TLS_VERIFY,
            transport=transport,
            trust_env=False,  # ARL 通常是本机/内网直连，不走系统代理
        )
        self._login_lock = threading.Lock()

    # ---------------------------------------------------------------- 认证

    def login(self) -> None:
        # 并发工具调用同时发现 token 失效时，只允许一个线程重新登录
        with self._login_lock:
            try:
                resp = self._http.post(
                    "/api/user/login",
                    json={"username": self._username, "password": self._password},
                )
            except httpx.HTTPError as e:
                raise ARLApiError(
                    -1,
                    f"连不上 ARL ({self.base_url})：{e}。"
                    f"请确认 ARL 已启动（docker compose up -d）且 ARL_URL 配置正确。",
                ) from e
            try:
                data = resp.json()
            except ValueError as e:
                raise ARLApiError(-1, f"登录响应非 JSON(HTTP {resp.status_code})") from e
            if data.get("code") != 200:
                raise ARLApiError(data.get("code"), f"登录失败: {data.get('message')}")
            self._token = data["data"]["token"]

    def _headers(self) -> dict:
        return {"Token": self._token} if self._token else {}

    # ---------------------------------------------------------------- 请求

    def request(self, method: str, path: str, *, params: dict | None = None,
                json_body: dict | None = None, raw: bool = False,
                _retry: bool = True):
        if not path.startswith("/api/"):
            raise ARLApiError(-1, "只允许访问 /api/ 前缀的 ARL 接口")
        if not self._token:
            self.login()
        try:
            resp = self._http.request(method, path, params=params,
                                      json=json_body, headers=self._headers())
        except httpx.HTTPError as e:
            raise ARLApiError(-1, f"ARL 请求失败: {e}") from e

        if raw:
            resp.raise_for_status()
            return resp.content

        try:
            data = resp.json()
        except ValueError as e:
            raise ARLApiError(-1, f"ARL 返回非 JSON(HTTP {resp.status_code}): "
                                  f"{resp.text[:200]}") from e
        if not isinstance(data, dict):
            raise ARLApiError(-1, "ARL 响应结构异常")

        code = data.get("code")
        if code == 401 and _retry and not self._static_token:
            self.login()  # token 失效（服务重启/换密码）后重登一次再重试
            return self.request(method, path, params=params, json_body=json_body,
                                raw=raw, _retry=False)
        if code == 401:
            raise ARLApiError(401, "Token 无效：检查 ARL_TOKEN 是否为 ARL 的有效 Token/API_KEY")
        if code != 200:
            raise ARLApiError(code, data.get("message", "未知错误"),
                              data.get("data"))
        return data

    # ---------------------------------------------------------------- 任务 CRUD

    def create_task(self, name: str, target: str, options: dict) -> list:
        """创建侦察任务，返回拆分后的任务列表（每项含 task_id）。"""
        body = {"name": name, "target": target, **(options or {})}
        data = self.request("POST", "/api/task/", json_body=body)
        items = data.get("items") or data.get("data", {}).get("items") or []
        if not items:
            raise ARLApiError(-1, f"任务创建返回异常: {data}")
        return items

    def list_tasks(self, page: int = 1, size: int = 20, order: str | None = None,
                   **filters) -> dict:
        params = {"page": page, "size": size, **filters}
        if order:
            params["order"] = order
        return self.request("GET", "/api/task/", params=params)

    def get_task(self, task_id: str) -> dict | None:
        data = self.list_tasks(size=1, **{"_id": task_id})
        items = data.get("items") or []
        return items[0] if items else None

    def stop_task(self, task_id: str) -> dict:
        return self.request("GET", f"/api/task/stop/{task_id}")

    def batch_stop_tasks(self, task_ids: list[str]) -> dict:
        return self.request("POST", "/api/task/batch_stop/",
                            json_body={"task_id": task_ids})

    def delete_tasks(self, task_ids: list[str], del_task_data: bool = False) -> dict:
        return self.request("POST", "/api/task/delete/",
                            json_body={"task_id": task_ids,
                                       "del_task_data": del_task_data})

    def restart_tasks(self, task_ids: list[str]) -> dict:
        return self.request("POST", "/api/task/restart/",
                            json_body={"task_id": task_ids})

    # ---------------------------------------------------------------- 资产/结果查询

    def query(self, collection: str, page: int = 1, size: int = 20,
              order: str | None = None, filters: dict | None = None) -> dict:
        if collection not in LIST_COLLECTIONS:
            raise ARLApiError(-1, f"不支持的集合: {collection}，"
                                  f"可选: {sorted(LIST_COLLECTIONS)}")
        params = {"page": page, "size": size}
        if order:
            params["order"] = order
        for k, v in (filters or {}).items():
            if v is not None and v != "":
                params[k] = v
        return self.request("GET", f"/api/{collection}/", params=params)

    def delete_assets(self, collection: str, ids: list[str]) -> dict:
        if collection not in DELETABLE_COLLECTIONS:
            raise ARLApiError(-1, f"不允许删除该集合: {collection}")
        return self.request("POST", f"/api/{collection}/delete/",
                            json_body={"_id": ids})

    def export_task(self, task_id: str) -> bytes:
        """下载任务 xlsx 报告（二进制）。"""
        return self.request("GET", f"/api/export/{task_id}", raw=True)

    def close(self) -> None:
        self._http.close()


# ---------------------------------------------------------------- 单例

_client: ARLClient | None = None
_client_lock = threading.Lock()


def get_client() -> ARLClient:
    global _client
    if _client is None:
        with _client_lock:  # FastMCP 工具在线程池并发执行，防止重复建连
            if _client is None:
                _client = ARLClient()
    return _client


def set_client(client: ARLClient | None) -> None:
    """测试注入用。"""
    global _client
    _client = client
