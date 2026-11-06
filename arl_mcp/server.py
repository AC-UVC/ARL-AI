"""MCP 工具层：把 ARL 能力 + 沙箱文件操作暴露给 AI。

启动（stdio 传输）:  python -m arl_mcp.server
"""

from __future__ import annotations

import json
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import config, fs_sandbox
from .arl_client import ARLApiError, ARLClient, get_client, set_client
from .url_guard import UrlBlocked, validate_url  # noqa: F401 (UrlBlocked 供工具层捕获)

mcp = FastMCP(
    "arl-mcp",
    instructions=(
        "ARL 资产侦察灯塔的 MCP。可用它创建/管理侦察任务、查询站点/域名/IP/"
        "漏洞结果，并把产物落盘到工作目录。文件操作被沙箱限制在工作目录内。"
    ),
    # streamable-http 的 Host/Origin 校验无法枚举部署环境的 IP/端口组合
    # （公网/局域网/回环可切换），故关闭；访问控制由强制 X-API-Key 鉴权承担。
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# ================================================================= ARL 任务

@mcp.tool()
def arl_ping() -> str:
    """连通性自检：登录 ARL 并读取控制台信息（CPU/内存/磁盘），确认 MCP 可用。"""
    c = get_client()
    info = c.request("GET", "/api/console/info")
    return _j({"base_url": c.base_url, "auth": "ok",
               "console": info.get("data")})


@mcp.tool()
def arl_create_task(
    name: str,
    target: str,
    domain_brute: bool = True,
    port_scan: bool = True,
    port_scan_type: str = "top100",
    service_detection: bool = False,
    site_identify: bool = True,
    nuclei_scan: bool = False,
    site_capture: bool = False,
    file_leak: bool = False,
    search_engines: bool = False,
    site_spider: bool = False,
    alt_dns: bool = False,
    ssl_cert: bool = False,
    os_detection: bool = False,
    web_info_hunter: bool = False,
    extra_options: dict | None = None,
) -> str:
    """创建 ARL 侦察任务。target 支持域名/IP/网段/URL，可混合（ARL 会自动拆成多个任务）。

    常用开关：domain_brute 子域爆破、port_scan(+port_scan_type: test/top100/top1000/all/custom)、
    site_identify 站点识别、nuclei_scan 漏洞扫描、site_capture 截图、file_leak 敏感文件、
    search_engines 搜索引擎、site_spider 爬虫、ssl_cert 证书、alt_dns 变形域名。
    其余冷门开关（如 domain_brute_type、port_custom、findvhost、dns_query_plugin、skip_scan_cdn_ip）
    通过 extra_options 传入。返回 items 里每个任务的 task_id 和 status。
    """
    options = {
        "domain_brute": domain_brute,
        "port_scan": port_scan,
        "port_scan_type": port_scan_type,
        "service_detection": service_detection,
        "site_identify": site_identify,
        "nuclei_scan": nuclei_scan,
        "site_capture": site_capture,
        "file_leak": file_leak,
        "search_engines": search_engines,
        "site_spider": site_spider,
        "alt_dns": alt_dns,
        "ssl_cert": ssl_cert,
        "os_detection": os_detection,
        "web_info_hunter": web_info_hunter,
        **(extra_options or {}),
    }
    items = get_client().create_task(name, target, options)
    return _j({"message": "任务已创建", "items": items})


@mcp.tool()
def arl_list_tasks(status: str = "", target: str = "", name: str = "",
                   task_tag: str = "", page: int = 1, size: int = 20,
                   order: str = "") -> str:
    """列出任务。status 可选 waiting/done/error/stop；task_tag 可选 task/risk_cruising。
    返回 {total, page, size, items:[...]}，进度看各任务 status 字段。"""
    filters = {k: v for k, v in
               {"status": status, "target": target, "name": name,
                "task_tag": task_tag}.items() if v}
    data = get_client().list_tasks(page=page, size=size,
                                   order=order or None, **filters)
    data.pop("query", None)
    return _j(data)


@mcp.tool()
def arl_get_task(task_id: str) -> str:
    """按 task_id 查任务详情（参数、目标、状态、统计）。"""
    task = get_client().get_task(task_id)
    if not task:
        return _j({"error": f"任务不存在: {task_id}"})
    return _j(task)


@mcp.tool()
def arl_stop_task(task_id: str) -> str:
    """停止一个运行中的任务。"""
    return _j(get_client().stop_task(task_id))


@mcp.tool()
def arl_delete_tasks(task_ids: list[str], del_task_data: bool = False) -> str:
    """删除已结束（done/stop/error）的任务；task_ids 为列表。del_task_data=True 时连结果数据一起删。
    运行中（waiting）的任务会拒绝删除，需先 arl_stop_task。"""
    return _j(get_client().delete_tasks(task_ids, del_task_data=del_task_data))


@mcp.tool()
def arl_restart_tasks(task_ids: list[str]) -> str:
    """重新下发（重启）一批任务。"""
    return _j(get_client().restart_tasks(task_ids))


# ================================================================= 资产查询

def _query(collection: str, task_id: str, page: int, size: int, order: str,
           filters: dict | None) -> str:
    f = dict(filters or {})
    if task_id:
        f["task_id"] = task_id  # ARL 中 task_id 为精确匹配
    data = get_client().query(collection, page=page, size=size,
                              order=order or None, filters=f)
    data.pop("query", None)
    return _j(data)


@mcp.tool()
def arl_query_sites(task_id: str = "", page: int = 1, size: int = 20,
                    order: str = "", filters: dict | None = None) -> str:
    """查询站点资产。filters 支持的字段（正则匹配）：site/hostname/ip/title/http_server/
    finger.name/status(整数)/favicon.hash/tag。task_id 精确过滤某任务的结果。"""
    return _query("site", task_id, page, size, order, filters)


@mcp.tool()
def arl_query_domains(task_id: str = "", page: int = 1, size: int = 20,
                      order: str = "", filters: dict | None = None) -> str:
    """查询域名解析记录。filters 支持：domain/record/type(A,CNAME等)/ips/source。"""
    return _query("domain", task_id, page, size, order, filters)


@mcp.tool()
def arl_query_ips(task_id: str = "", page: int = 1, size: int = 20,
                  order: str = "", filters: dict | None = None) -> str:
    """查询 IP 资产。filters 支持：ip/domain/port_info.port_id/port_info.service_name/
    port_info.product/os_info.name/ip_type(PUBLIC/PRIVATE)/cdn_name/geo_city.region_name。"""
    return _query("ip", task_id, page, size, order, filters)


@mcp.tool()
def arl_query_nuclei(task_id: str = "", page: int = 1, size: int = 20,
                     order: str = "", filters: dict | None = None) -> str:
    """查询 nuclei 漏洞结果。filters 支持：vuln_name/vuln_severity(critical,high,medium,low)/
    vuln_url/template_id/curl_command/target。"""
    return _query("nuclei_result", task_id, page, size, order, filters)


@mcp.tool()
def arl_query_urls(task_id: str = "", page: int = 1, size: int = 20,
                   order: str = "", filters: dict | None = None) -> str:
    """查询敏感 URL / 文件泄露记录。filters 支持：url/website/website_title/length。"""
    return _query("url", task_id, page, size, order, filters)


@mcp.tool()
def arl_list_pocs(page: int = 1, size: int = 20,
                  filters: dict | None = None) -> str:
    """查询 PoC 库。filters 支持：plugin_name/app_name/scheme/vul_name/plugin_type(poc,brute)/category。"""
    return _query("poc", "", page, size, "", filters)


@mcp.tool()
def arl_query_any(collection: str, task_id: str = "", page: int = 1,
                  size: int = 20, order: str = "",
                  filters: dict | None = None) -> str:
    """通用查询：collection 可选 site/domain/ip/url/cert/service/fileleak/cip/wih/
    nuclei_result/vuln/fingerprint/stat_finger/asset_scope/asset_site/asset_domain/
    asset_ip/task 等。专用工具（arl_query_sites 等）够用时就别用这个。"""
    return _query(collection, task_id, page, size, order, filters)


@mcp.tool()
def arl_delete_assets(collection: str, ids: list[str]) -> str:
    """删除资产记录（collection 可选 site/domain/ip/url/cert/fileleak/wih/nuclei_result/vuln）。
    ids 为这些记录的 _id 列表。删任务请用 arl_delete_tasks。"""
    return _j(get_client().delete_assets(collection, ids))


@mcp.tool()
def arl_export_task(task_id: str, filename: str = "") -> str:
    """下载任务的 xlsx 报告并保存到工作目录（沙箱内），返回保存路径。"""
    data = get_client().export_task(task_id)
    fname = filename or f"ARL报告_{task_id}.xlsx"
    if not fname.endswith(".xlsx"):
        fname += ".xlsx"
    path = fs_sandbox.fs_write(fname, data)
    return _j({"path": str(path), "size": len(data)})


@mcp.tool()
def arl_api_call(method: str, path: str, params: dict | None = None,
                 body: dict | None = None) -> str:
    """逃生舱口：直接调用任意 ARL /api/ 接口（method: GET/POST/PUT/DELETE，path 必须以 /api/ 开头）。
    前面 20 个专用工具覆盖不到的接口（如 asset_scope 添加、task_fofa 提交）用它。"""
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return _j({"error": f"不支持的方法: {method}"})
    data = get_client().request(method, path, params=params, json_body=body)
    return _j(data)


# ================================================================= 沙箱文件操作

@mcp.tool()
def fs_read(path: str) -> str:
    """读取工作目录内的文本文件（超出工作目录一律拒绝）。"""
    return fs_sandbox.fs_read(path)


@mcp.tool()
def fs_write(path: str, content: str, append: bool = False) -> str:
    """写文本文件到工作目录内（自动建父目录；append=True 追加）。临时文件请用 fs_temp_file。"""
    p = fs_sandbox.fs_write(path, content, append=append)
    return _j({"path": str(p)})


@mcp.tool()
def fs_list(path: str = ".") -> str:
    """列目录（默认工作目录根）。返回每个条目的名字/类型/大小。"""
    return _j(fs_sandbox.fs_list(path))


@mcp.tool()
def fs_mkdir(path: str) -> str:
    """在工作目录内创建目录。"""
    p = fs_sandbox.fs_mkdir(path)
    return _j({"path": str(p)})


@mcp.tool()
def fs_delete(path: str) -> str:
    """删除工作目录内的文件或目录（整个目录递归删，谨慎）。"""
    return fs_sandbox.fs_delete(path)


@mcp.tool()
def fs_temp_file(suffix: str = "") -> str:
    """创建一个临时文件（唯一合法位置：工作目录/.tmp/），返回路径。中间产物、
    下载缓存等一律写这里，用完可 fs_delete 或 fs_clean_tmp 清理。"""
    p = fs_sandbox.temp_file(suffix=suffix)
    return _j({"path": str(p)})


@mcp.tool()
def fs_clean_tmp() -> str:
    """清空工作目录/.tmp/ 下所有临时内容。"""
    n = fs_sandbox.clean_tmp()
    return _j({"cleaned": n})


# ================================================================= 网络工具

@mcp.tool()
def fetch_url(url: str, max_bytes: int = 20000) -> str:
    """安全抓取一个公网 URL 的响应文本（快速看一眼页面/接口内容用，资产收集请走 arl_create_task）。
    仅允许 http/https；拒绝 localhost/内网/保留地址；重定向逐跳校验，导向内网即中断。"""
    try:
        current = validate_url(url)
    except UrlBlocked as e:
        return _j({"error": f"URL 被拦截: {e}"})
    try:
        resp = httpx.get(current, timeout=15, follow_redirects=False,
                         headers={"User-Agent": "ARL-MCP/1.0"})
    except httpx.HTTPError as e:
        return _j({"error": f"请求失败: {e}"})
    for _ in range(5):
        if resp.status_code not in (301, 302, 303, 307, 308):
            break
        loc = resp.headers.get("location", "")
        if not loc:
            break
        try:
            current = validate_url(urljoin(str(resp.url), loc))
        except UrlBlocked as e:
            return _j({"error": f"重定向被拦截: {e}"})
        try:
            resp = httpx.get(current, timeout=15, follow_redirects=False,
                             headers={"User-Agent": "ARL-MCP/1.0"})
        except httpx.HTTPError as e:
            return _j({"error": f"跟随重定向失败: {e}"})
    text = resp.text
    if len(text) > max_bytes:
        text = text[:max_bytes] + f"\n...[截断，共 {len(text)} 字符]"
    return _j({"url": str(resp.url), "status": resp.status_code,
               "content_type": resp.headers.get("content-type", ""),
               "body": text})


# ================================================================= 入口

def main() -> None:
    mcp.run()  # stdio 传输


if __name__ == "__main__":
    main()
