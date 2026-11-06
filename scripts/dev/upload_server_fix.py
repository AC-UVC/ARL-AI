"""上传 transport_security 修复版 server.py，重启服务，验证局域网 MCP 客户端。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(ROOT, "arl_mcp", "server.py")
REMOTE = "/root/ARL-AI/arl_mcp/server.py"


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
    sftp.put(LOCAL, REMOTE)
    sftp.close()
    print("server.py(transport_security 修复版) 已上传")

    run("systemctl restart mcp-ai && sleep 4 && systemctl is-active mcp-ai")
    c.close()


if __name__ == "__main__":
    main()
