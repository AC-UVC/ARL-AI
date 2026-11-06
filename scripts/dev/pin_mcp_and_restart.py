"""Kali venv 固定 mcp 1.x 并重启 mcp-ai 服务，验证管理 API。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, username="root", password="kali", timeout=8,
          allow_agent=False, look_for_keys=False)


def run(cmd, timeout=600):
    _, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    rc = out.channel.recv_exit_status()
    if o.strip():
        print(o.strip()[-800:])
    if e.strip():
        print("[stderr]", e.strip()[-400:])
    if rc != 0:
        raise SystemExit(f"rc={rc}: {cmd}")
    return o


run("/root/ARL-AI/.venv/bin/pip install -q 'mcp>=1.2,<2' "
    "-i https://pypi.tuna.tsinghua.edu.cn/simple")
run("/root/ARL-AI/.venv/bin/pip show mcp | head -2")
run("systemctl restart mcp-ai && sleep 5 && systemctl is-active mcp-ai")
run("curl -s http://127.0.0.1:8000/admin/config && echo ' <- 直连 :8000'")
run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- 经 nginx 代理'")
run("curl -sk -o /dev/null -w 'web %{http_code}\\n' https://127.0.0.1:5004/")
c.close()
print("OK")
