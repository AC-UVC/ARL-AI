"""端到端冒烟：以 stdio 传输真实拉起 MCP 服务器，列出工具并实际调用。

用法（工作目录下）:
    .venv/Scripts/python.exe scripts/smoke_stdio.py
"""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "arl_mcp.server"],
        cwd=ROOT,
        env={**os.environ,
             "PYTHONPATH": ROOT,
             "ARL_MCP_WORKSPACE": ROOT},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"[1] 工具数量: {len(names)}")
            print("    ", ", ".join(sorted(names)))

            res = await session.call_tool(
                "fs_write", {"path": "冒烟测试/hello.txt",
                             "content": "ARL MCP 沙箱 OK"})
            print("[2] fs_write ->", res.content[0].text)

            res = await session.call_tool("fs_read",
                                          {"path": "冒烟测试/hello.txt"})
            print("[3] fs_read  ->", res.content[0].text)

            res = await session.call_tool("fs_write",
                                          {"path": "../逃逸.txt", "content": "x"})
            print("[4] 越界写入 ->", res.content[0].text[:80])

            res = await session.call_tool("fs_delete",
                                          {"path": "冒烟测试"})
            print("[5] 清理 ->", res.content[0].text)

            escaped = await session.call_tool(
                "fs_write", {"path": "../逃逸.txt", "content": "x"})
            if escaped.isError:
                print("[6] 沙箱拒绝越界写入：通过")


if __name__ == "__main__":
    asyncio.run(main())
