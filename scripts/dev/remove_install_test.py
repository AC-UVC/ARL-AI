"""删除一键安装测试实例（按 install.sh 输出的卸载命令），保留验收环境。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd, timeout=300):
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        print(f"$ {cmd}\n{o.strip()[-400:]}")
        if e.strip():
            print("[stderr]", e.strip()[-300:])
        return rc

    run("cd /opt/docker_arl_ai2 && docker compose down -v")
    run("systemctl disable --now mcp-ai2 2>/dev/null; "
        "rm -f /etc/systemd/system/mcp-ai2.service; systemctl daemon-reload")
    run("rm -rf /opt/docker_arl_ai2 /root/arl-install")
    run("docker ps -a --format '{{.Names}}' | grep arl_ai2 || echo '容器已清空'")
    run("ss -lnt | grep -E ':5006|:5007|:8020|:8021' || echo '端口已释放'")
    c.close()


if __name__ == "__main__":
    main()
