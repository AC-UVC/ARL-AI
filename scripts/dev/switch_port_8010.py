"""端口切换 8000→8010：更新面板 JS、nginx 代理、服务端口，全部重载并验证。"""

import os

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
            print(o.strip()[-900:])
        if e.strip():
            print("[stderr]", e.strip()[-400:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    sftp = c.open_sftp()

    # 1. 更新前端面板（PORT=8010）+ index.html 缓存版本
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    html = html.replace("mcp_panel.js?v=1", "mcp_panel.js?v=2")
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")
    print("前端面板已更新为 8010，index.html 缓存版本 v=2")

    # 2. nginx 代理配置
    sftp.put(os.path.join(DEPLOY, "mcp_admin.conf"), f"{ARD}/mcp_admin.conf")
    run("docker exec arl_ai_web nginx -t && docker exec arl_ai_web nginx -s reload")

    # 3. MCP 服务端 + systemd 单元（8010）
    sftp.put(os.path.join(DEPLOY, "mcp_service.py"), f"{RAI}/mcp_service.py")
    unit_local = os.path.join(ROOT, ".tmp", "mcp-ai.service")
    open(unit_local, "w").write(UNIT)
    sftp.put(unit_local, "/etc/systemd/system/mcp-ai.service")
    sftp.close()
    run("systemctl daemon-reload && systemctl restart mcp-ai && sleep 4"
        " && systemctl is-active mcp-ai")

    # 4. 验证
    run("curl -s http://127.0.0.1:8010/admin/config && echo ' <- 直连 :8010'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- nginx 代理'")
    run("curl -sk -o /dev/null -w 'web %{http_code}\\n' https://127.0.0.1:5004/")
    run("curl -sk https://127.0.0.1:5004/ | grep -o 'mcp_panel.js?v=2' | head -1")
    c.close()
    print("端口切换完成")


if __name__ == "__main__":
    main()
