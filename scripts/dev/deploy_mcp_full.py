"""完整部署：前端注入 MCP 栏目 + MCP HTTP 服务 + systemd + 验证。

步骤：
1. 从 arl_ai_web 容器拷出前端 /code/frontend
2. 注入 mcp_panel.js（导航栏 MCP 栏目 + 面板）
3. 挂载前端回容器、nginx 加 /mcp_admin/ 代理、mongo 暴露 127.0.0.1:27019
4. /root/ARL-AI 部署 MCP HTTP 服务（FastMCP streamable-http :8000）
5. systemd 托管 + 验证
"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(ROOT, "scripts", "deploy")
ARD = "/opt/docker_arl_ai"
RAI = "/root/ARL-AI"

UNIT = """[Unit]
Description=ARL MCP Service (FastMCP streamable-http)
After=network.target docker.service

[Service]
WorkingDirectory={rai}
Environment=PYTHONPATH={rai}
Environment=ARL_URL=https://127.0.0.1:5004
Environment=ARL_MCP_WORKSPACE={rai}
Environment=ARL_USER=admin
Environment=ARL_PASS=arlpass
Environment=MCP_PORT=8010
ExecStart={rai}/.venv/bin/python {rai}/mcp_service.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
""".format(rai=RAI)

ARL_FILES = [
    "arl_mcp/__init__.py", "arl_mcp/config.py", "arl_mcp/fs_sandbox.py",
    "arl_mcp/url_guard.py", "arl_mcp/arl_client.py", "arl_mcp/server.py",
    "arl_mcp/__main__.py",
]


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd, timeout=300, fatal=True):
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        if o.strip():
            print(o.strip()[-1200:])
        if e.strip():
            print("[stderr]", e.strip()[-600:])
        if rc != 0 and fatal:
            raise SystemExit(f"失败 rc={rc}: {cmd}")
        return o

    sftp = c.open_sftp()

    # 1. 拷出前端
    print("== 1. 拷出前端 ==")
    run(f"rm -rf {ARD}/frontend && docker cp arl_ai_web:/code/frontend {ARD}/frontend")
    run(f"du -sh {ARD}/frontend && ls {ARD}/frontend")

    # 2. 注入面板脚本 + 改 index.html
    print("== 2. 注入前端 ==")
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    os.makedirs(os.path.dirname(idx_local), exist_ok=True)
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    tag = '<script src=/mcp_panel.js?v=1></script>'
    if 'mcp_panel.js' not in html:
        low = html.lower()
        if '</body>' in low:
            i = low.rindex('</body>')
            html = html[:i] + tag + html[i:]
        else:
            html += tag
        open(idx_local, "w", encoding="utf-8").write(html)
        sftp.put(idx_local, f"{ARD}/frontend/index.html")
        print("index.html 已注入 mcp_panel.js")
    else:
        print("index.html 已含注入，跳过")

    # 3. 上传 nginx 代理配置 + 新 compose
    print("== 3. 上传配置 ==")
    sftp.put(os.path.join(DEPLOY, "mcp_admin.conf"), f"{ARD}/mcp_admin.conf")
    sftp.put(os.path.join(DEPLOY, "docker-compose.arl-ai.yml"),
             f"{ARD}/docker-compose.yml")
    run(f"grep -n 'include' /etc/nginx/nginx.conf | head -2")

    # 4. MCP 服务端文件 → /root/ARL-AI
    print("== 4. 上传 MCP 服务端 ==")
    run(f"mkdir -p {RAI}/arl_mcp")
    for f in ARL_FILES:
        sftp.put(os.path.join(ROOT, f), f"{RAI}/{f}")
    sftp.put(os.path.join(DEPLOY, "mcp_service.py"), f"{RAI}/mcp_service.py")
    sftp.close()

    # 5. Kali venv + 依赖
    print("== 5. Kali 依赖 ==")
    run(f"test -x {RAI}/.venv/bin/python || python3 -m venv {RAI}/.venv", timeout=180)
    run(f"{RAI}/.venv/bin/pip install -q mcp httpx pymongo uvicorn "
        f"-i https://pypi.tuna.tsinghua.edu.cn/simple", timeout=900)

    # 6. systemd 托管 MCP 服务
    print("== 6. systemd 托管 ==")
    unit_local = os.path.join(ROOT, ".tmp", "mcp-ai.service")
    open(unit_local, "w").write(UNIT)
    sftp = c.open_sftp()
    sftp.put(unit_local, "/etc/systemd/system/mcp-ai.service")
    sftp.close()
    run("systemctl daemon-reload && systemctl enable --now mcp-ai.service")

    # 7. 重建容器（挂载前端/代理配置、mongo 端口）
    print("== 7. 重建容器 ==")
    run(f"cd {ARD} && docker compose up -d", timeout=300)
    run("sleep 6 && docker ps --format '{{.Names}}\\t{{.Status}}' | grep arl_ai")

    # 8. 验证
    print("== 8. 验证 ==")
    run("curl -sk -o /dev/null -w 'web %{http_code}\\n' https://127.0.0.1:5004/")
    run("sleep 3; curl -sk https://127.0.0.1:5004/mcp_admin/config && echo")
    run("curl -s http://127.0.0.1:8000/admin/config && echo")
    run("curl -sk https://127.0.0.1:5004/ | grep -o mcp_panel.js | head -1")
    run("systemctl is-active mcp-ai.service")

    cfg = run("curl -s http://127.0.0.1:8000/admin/config")
    c.close()
    print("\n部署完成。MCP 服务地址: http://%s:8000/mcp" % HOST)
    print("UI 面板: https://%s:5004  导航栏最右侧「MCP」" % HOST)


if __name__ == "__main__":
    main()
