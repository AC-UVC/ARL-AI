"""同步部署前 bug 修复到 Kali：server/arl_client/mcp_service/panel，回归验证。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARD = "/opt/docker_arl_ai"
RAI = "/root/ARL-AI"

UPLOADS = [
    ("arl_mcp/server.py", f"{RAI}/arl_mcp/server.py"),
    ("arl_mcp/arl_client.py", f"{RAI}/arl_mcp/arl_client.py"),
    ("scripts/deploy/mcp_service.py", f"{RAI}/mcp_service.py"),
    ("scripts/deploy/mcp_panel.js", f"{ARD}/frontend/mcp_panel.js"),
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
            print(o.strip()[-700:])
        if e.strip():
            print("[stderr]", e.strip()[-400:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    sftp = c.open_sftp()
    for local_rel, remote in UPLOADS:
        sftp.put(os.path.join(ROOT, local_rel), remote)
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    import re
    html = open(idx_local, encoding="utf-8").read()
    html = re.sub(r"mcp_panel\.js\?v=\d+", "mcp_panel.js?v=9", html)
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")
    sftp.close()
    print(f"已同步 {len(UPLOADS)} 个文件，index v9")

    run("systemctl restart mcp-ai && sleep 4 && systemctl is-active mcp-ai")
    run("curl -s http://127.0.0.1:5005/mcp_admin/config | head -c 200 && echo")
    run("curl -s -o /dev/null -w '无密钥: %{http_code}\\n' -X POST "
        "http://127.0.0.1:8010/mcp -H 'Content-Type: application/json' -d '{}'",
        fatal=False)
    c.close()


if __name__ == "__main__":
    main()
