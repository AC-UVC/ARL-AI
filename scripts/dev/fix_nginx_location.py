"""nginx 修正：把 /mcp_admin/ 代理 location 注入 443 server 块（挂载整个 nginx.conf）。

同时补上端口切换脚本上次没跑完的部分：mcp_service.py + systemd 单元（8010）。
"""

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

LOCATION_BLOCK = """
        # MCP 管理面板同源代理（经宿主机 8010 的 MCP 服务）
        location /mcp_admin/ {
            proxy_pass http://host.docker.internal:8010/admin/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 5s;
            proxy_read_timeout 30s;
        }
"""


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

    # 1. 取容器内 nginx.conf，注入 location 到 443 server（error_page 497 前）
    print("== 1. 注入 nginx location ==")
    _, out, _ = c.exec_command("docker exec arl_ai_web cat /etc/nginx/nginx.conf")
    conf = out.read().decode("utf-8")
    marker = "        error_page 497"
    if "/mcp_admin/" not in conf:
        i = conf.index(marker)
        conf = conf[:i] + LOCATION_BLOCK + "\n" + conf[i:]
    tmp = os.path.join(ROOT, ".tmp", "nginx.conf")
    open(tmp, "w", encoding="utf-8").write(conf)
    sftp.put(tmp, f"{ARD}/nginx.conf")

    # 2. 更新 compose（挂载 nginx.conf，去掉 conf.d 挂载）
    sftp.put(os.path.join(DEPLOY, "docker-compose.arl-ai.yml"),
             f"{ARD}/docker-compose.yml")

    # 3. MCP 服务端 + systemd 单元（8010）
    sftp.put(os.path.join(DEPLOY, "mcp_service.py"), f"{RAI}/mcp_service.py")
    unit_local = os.path.join(ROOT, ".tmp", "mcp-ai.service")
    open(unit_local, "w").write(UNIT)
    sftp.put(unit_local, "/etc/systemd/system/mcp-ai.service")
    sftp.close()

    # 4. 重建 web 容器 + 重启 MCP 服务
    print("== 2. 重建容器 + 重启服务 ==")
    run(f"cd {ARD} && docker compose up -d", timeout=300)
    run("systemctl daemon-reload && systemctl restart mcp-ai && sleep 4"
        " && systemctl is-active mcp-ai")

    # 5. 验证
    print("== 3. 验证 ==")
    run("sleep 8; curl -sk -o /dev/null -w 'web %{http_code}\\n' https://127.0.0.1:5004/")
    run("curl -s http://127.0.0.1:8010/admin/config && echo ' <- 直连 :8010'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- nginx 代理'")
    run("curl -sk https://127.0.0.1:5004/ | grep -o 'mcp_panel.js?v=2' | head -1")
    c.close()
    print("全部完成")


if __name__ == "__main__":
    main()
