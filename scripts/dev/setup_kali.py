"""Kali 部署脚本：上传 compose、准备目录、启动新 ARL 容器组。

用法: python setup_kali.py
"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
LOCAL_COMPOSE = os.path.join(os.path.dirname(__file__), "docker-compose.arl-ai.yml")
REMOTE_DIR = "/opt/docker_arl_ai"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd: str, timeout: int = 120) -> str:
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        print(f"$ {cmd}\n{o}{('[stderr] ' + e) if e.strip() else ''}")
        if rc != 0:
            print(f"[rc={rc}]")
        return o

    # 1. 建目录（幂等）
    run("mkdir -p /opt/docker_arl_ai /tmp/arl_ai_test")

    # 2. SFTP 上传 compose
    sftp = c.open_sftp()
    sftp.put(LOCAL_COMPOSE, f"{REMOTE_DIR}/docker-compose.yml")
    st = sftp.stat(f"{REMOTE_DIR}/docker-compose.yml")
    print(f"compose 已上传 ({st.st_size} bytes)")
    sftp.close()

    # 3. 从原灯塔目录复制配置与静态资源（不改原目录任何内容）
    run(f"cp -a /opt/docker_arl/config-docker.yaml {REMOTE_DIR}/config-docker.yaml")
    run(f"cp -a /opt/docker_arl/mongo-init.js {REMOTE_DIR}/mongo-init.js")
    run(f"cp -a /opt/docker_arl/poc {REMOTE_DIR}/poc")
    run(f"touch {REMOTE_DIR}/arl_web.log {REMOTE_DIR}/arl_worker.log")

    # 4. 启动新 ARL 容器组
    run(f"cd {REMOTE_DIR} && docker compose up -d", timeout=300)

    # 5. 状态确认
    run("docker ps --format '{{.Names}}\\t{{.Status}}' | grep arl_ai")
    c.close()
    print("部署完成")


if __name__ == "__main__":
    main()
