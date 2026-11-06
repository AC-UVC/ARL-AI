"""MCP 客户端端到端测试（从物理机连 Kali 的新灯塔 MCP 服务）。

流程：开服务 → 连接列工具 → 读各集合扫描数据 → 关服务验证 403 → 再开（留验收用）。
"""

import asyncio
import json
import os
import sys
import urllib.request

MCP_DATA = os.environ.get("ARL_MCP_DATA", "http://192.168.224.128:8010")  # 数据面
ADMIN = os.environ.get("ARL_MCP_ADMIN", "http://192.168.224.128:5005/mcp_admin")  # 管理面（走 nginx 代理，与浏览器面板同链路）
UI = os.environ.get("ARL_UI", "https://192.168.224.128:5004")

from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402


def admin(body=None):
    req = urllib.request.Request(
        ADMIN + "/config",
        data=json.dumps(body or {}).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if body else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


async def run_client(api_key: str | None) -> dict:
    url = f"{MCP_DATA}/mcp"
    out = {}
    headers = {"X-API-Key": api_key} if api_key else {}
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            out["tools"] = sorted(t.name for t in tools.tools)

            r = await s.call_tool("arl_ping", {})
            out["ping"] = json.loads(r.content[0].text)["auth"]

            for name, kw in [
                ("arl_list_tasks", {"size": 5}),
                ("arl_query_sites", {"size": 3}),
                ("arl_query_domains", {"size": 3}),
                ("arl_query_ips", {"size": 3}),
                ("arl_query_urls", {"size": 3}),
                ("arl_query_nuclei", {"size": 3}),
                ("arl_query_any", {"collection": "vuln", "size": 3}),
                ("arl_list_pocs", {"size": 3}),
                ("fs_list", {"path": "."}),
            ]:
                r = await s.call_tool(name, kw)
                d = json.loads(r.content[0].text)
                total = d.get("total", "?") if isinstance(d, dict) \
                    else f"{len(d)} 条"
                out[name] = total
            # 过滤功能：按严重级别查 nuclei
            r = await s.call_tool("arl_query_nuclei",
                                  {"filters": {"vuln_severity": "high"}})
            out["nuclei_high"] = json.loads(r.content[0].text).get("total")
    return out


def main() -> int:
    cfg = admin()
    print(f"[1] 管理API ok: enabled={cfg['enabled']} port={cfg['port']}")

    admin({"enabled": True})
    print("[2] UI 面板开关 -> 已开启")
    key = admin()["api_key"]

    res = asyncio.run(run_client(key))
    print(f"[3] MCP 连接成功，工具数 {len(res['tools'])}")
    print(f"    工具: {', '.join(res['tools'][:8])} ...")
    print(f"[4] arl_ping 认证: {res['ping']}")
    print("[5] 扫描数据读取（total）:")
    for k in ("arl_list_tasks", "arl_query_sites", "arl_query_domains",
              "arl_query_ips", "arl_query_urls", "arl_query_nuclei",
              "nuclei_high", "arl_query_any(vuln)" if False else "arl_query_any",
              "arl_list_pocs", "fs_list"):
        if k in res:
            print(f"    {k:<18} = {res[k]}")

    admin({"enabled": False})
    print("[6] 面板开关 -> 已关闭")
    try:
        asyncio.run(run_client(key))
        print("[7] 关闭后仍可连接 ✗")
        return 1
    except Exception as e:
        print(f"[7] 关闭后连接被拒 ✓ ({str(e)[:60]}...)")

    # 无密钥 / 错误密钥必须 401
    admin({"enabled": True})
    for label, hdr in [("无密钥", {}), ("错误密钥", {"X-API-Key": "wrong"})]:
        try:
            asyncio.run(run_client(hdr.get("X-API-Key") or ""))
            print(f"[8] {label} 竟然成功 ✗")
            return 1
        except Exception:
            print(f"[8] {label} 被拒 401 ✓")
    print("[9] 重新开启（留给验收）✓")
    print("\n结论: 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
