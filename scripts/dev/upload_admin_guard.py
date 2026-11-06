"""上传管理面来源校验版 mcp_service.py，重启并全链路验证。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(ROOT, "scripts", "deploy", "mcp_service.py")
REMOTE = "/root/ARL-AI/mcp_service.py"


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
    sftp.put(LOCAL, REMOTE)
    sftp.close()
    print("mcp_service.py(来源校验版) 已上传")

    run("systemctl restart mcp-ai && sleep 4 && systemctl is-active mcp-ai")
    run("curl -s http://127.0.0.1:8011/admin/config && echo ' <- 管理面 8011'")
    run("curl -s http://127.0.0.1:5005/mcp_admin/config && echo ' <- HTTP:5005 代理'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- HTTPS:5004 代理'")
    run("curl -s -o /dev/null -w '数据面8010无密钥: %{http_code}\\n' "
        "-X POST http://127.0.0.1:8010/mcp -H 'Content-Type: application/json' -d '{}'",
        fatal=False)
    c.close()


if __name__ == "__main__":
    main()
