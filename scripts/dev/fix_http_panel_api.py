"""80 server 块也注入 /mcp_admin/ location（HTTP :5005 面板同源代理），
更新面板 JS 文案，index bump v4，重载 nginx 并验证两个端口。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(ROOT, "scripts", "deploy")
ARD = "/opt/docker_arl_ai"

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
            print(o.strip()[-700:])
        if e.strip():
            print("[stderr]", e.strip()[-300:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    sftp = c.open_sftp()

    # 1. 面板 JS（文案修正）
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")

    # 2. index bump v4
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    html = html.replace("mcp_panel.js?v=3", "mcp_panel.js?v=4")
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")

    # 3. nginx：80 server（第一处 swaggerui 前）也注入 location
    _, out, _ = c.exec_command("docker exec arl_ai_web cat /etc/nginx/nginx.conf")
    conf = out.read().decode("utf-8")
    count = conf.count("/mcp_admin/")
    if count == 1:  # 目前只有 443 server 注入
        marker = "        location /swaggerui/"
        i = conf.index(marker)  # 第一处属于 80 server
        conf = conf[:i] + LOCATION_BLOCK + "\n" + conf[i:]
        tmp = os.path.join(ROOT, ".tmp", "nginx.conf")
        open(tmp, "w", encoding="utf-8").write(conf)
        sftp.put(tmp, f"{ARD}/nginx.conf")
        print(f"nginx 80 server 已注入（此前 /mcp_admin/ 出现 {count} 次）")
    else:
        print(f"/mcp_admin/ 已出现 {count} 次，跳过注入")
    sftp.close()

    # 4. 重载 nginx 并验证两个端口的面板 API
    run("docker exec arl_ai_web nginx -t && docker exec arl_ai_web nginx -s reload")
    run("curl -s http://127.0.0.1:5005/mcp_admin/config && echo ' <- HTTP:5005'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- HTTPS:5004'")
    c.close()


if __name__ == "__main__":
    main()
