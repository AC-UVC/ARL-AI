"""Kali 上真实执行一键安装（独立端口/目录/服务名，不碰验收环境）。

python run_install_test.py  ==  bash /root/arl-install/install.sh \
  --web-port 5006 --http-port 5007 --mcp-port 8020 --admin-port 8021 \
  --prefix arl_ai2 --dir /opt/docker_arl_ai2 --service mcp-ai2
"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)
    _, out, err = c.exec_command(
        "bash /root/arl-install/install.sh "
        "--web-port 5006 --http-port 5007 --mcp-port 8020 --admin-port 8021 "
        "--prefix arl_ai2 --dir /opt/docker_arl_ai2 --service mcp-ai2",
        timeout=560)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    rc = out.channel.recv_exit_status()
    tail = o[-2500:] if len(o) > 2500 else o
    print(tail)
    if e.strip():
        print("[stderr]", e.strip()[-800:])
    print(f"[安装脚本 rc={rc}]")
    c.close()


if __name__ == "__main__":
    main()
