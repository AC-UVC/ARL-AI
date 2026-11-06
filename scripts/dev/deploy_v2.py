"""部署 v2：管理面固定 8011 / 数据面端口可选 / X-API-Key 鉴权 / 面板 UI 升级。"""

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
Environment=MCP_ADMIN_PORT=8011
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
            print(o.strip()[-700:])
        if e.strip():
            print("[stderr]", e.strip()[-400:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    sftp = c.open_sftp()

    # 1. 服务端 v2 + 面板 v2
    sftp.put(os.path.join(DEPLOY, "mcp_service.py"), f"{RAI}/mcp_service.py")
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")

    # 2. index bump v5
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    html = html.replace("mcp_panel.js?v=4", "mcp_panel.js?v=5")
    if "mcp_panel.js?v=5" not in html:
        html = html.replace("mcp_panel.js?v=3", "mcp_panel.js?v=5")
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")

    # 3. nginx：管理面代理 8010 -> 8011（数据面端口改为用户可选，代理固定走管理面）
    _, out, _ = c.exec_command(f"cat {ARD}/nginx.conf")
    conf = out.read().decode("utf-8")
    if ":8011/admin/" not in conf:
        conf = conf.replace(":8010/admin/", ":8011/admin/")
        tmp = os.path.join(ROOT, ".tmp", "nginx.conf")
        open(tmp, "w", encoding="utf-8").write(conf)
        sftp.put(tmp, f"{ARD}/nginx.conf")
        print("nginx 代理已切到管理面 8011")

    # 4. systemd unit（加 MCP_ADMIN_PORT）
    unit_local = os.path.join(ROOT, ".tmp", "mcp-ai.service")
    open(unit_local, "w").write(UNIT)
    sftp.put(unit_local, "/etc/systemd/system/mcp-ai.service")
    sftp.close()

    # 5. 重启服务 + 重载 nginx
    run("systemctl daemon-reload && systemctl restart mcp-ai && sleep 4"
        " && systemctl is-active mcp-ai")
    run("docker exec arl_ai_web nginx -t && docker exec arl_ai_web nginx -s reload")

    # 6. 验证
    run("curl -s http://127.0.0.1:8011/admin/config && echo ' <- 管理面 8011'")
    run("curl -s http://127.0.0.1:5005/mcp_admin/config && echo ' <- HTTP:5005 代理'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- HTTPS:5004 代理'")
    run("curl -s -o /dev/null -w '数据面8010无密钥: %{http_code}\\n' "
        "-X POST http://127.0.0.1:8010/mcp -H 'Content-Type: application/json' -d '{}'",
        fatal=False)
    c.close()
    print("部署 v2 完成")


if __name__ == "__main__":
    main()
