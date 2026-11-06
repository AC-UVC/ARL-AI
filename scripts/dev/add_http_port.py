"""追加 HTTP 端口 5005:80 映射，重建 web 容器并验证。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_COMPOSE = os.path.join(ROOT, "scripts", "deploy", "docker-compose.arl-ai.yml")
ARD = "/opt/docker_arl_ai"


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
    sftp.put(LOCAL_COMPOSE, f"{ARD}/docker-compose.yml")
    sftp.close()
    run(f"cd {ARD} && docker compose up -d", timeout=300)
    run("sleep 8; curl -s -o /dev/null -w 'http80 %{http_code}\\n' "
        "http://127.0.0.1:5005/")
    run("curl -sk -o /dev/null -w 'https443 %{http_code}\\n' "
        "https://127.0.0.1:5004/")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo")
    c.close()


if __name__ == "__main__":
    main()
