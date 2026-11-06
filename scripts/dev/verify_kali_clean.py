"""Kali 残留深度排查：全盘文件系统找 ARL-AI 测试痕迹并补删（原灯塔/ARL-Next 不动）。"""

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
        out.channel.recv_exit_status()
        print(f"$ {cmd[:90]}")
        if o.strip():
            print(o.strip())
        if e.strip():
            print("[stderr]", e.strip()[-200:])
        return o

    print("=== 1. mongodump 临时归档（上轮清理遗漏点）===")
    run("ls -lh /tmp/arl_ai_test/ 2>/dev/null || echo '不存在'")
    run("rm -rf /tmp/arl_ai_test /tmp/test1.txt /opt/test2.txt "
        "/root/.cache/pip 2>/dev/null; "
        "ls /tmp/test1.txt /tmp/arl_ai_test 2>&1 | grep -c 'No such' "
        "&& echo '[OK] dump 归档与调试残留已删'")

    print("=== 2. 全盘关键路径搜索 ARL-AI 痕迹 ===")
    run("find /tmp /var/tmp /root /opt /home /etc/systemd/system -maxdepth 4 "
        "\\( -iname '*arl_ai*' -o -iname '*mcp-ai*' -o -iname 'mcp_panel.js' "
        "-o -iname 'mcp_service.py' -o -iname 'mcp_config.json' \\) 2>/dev/null "
        "| grep -v docker/overlay2 || echo '[OK] 文件系统无残留'")

    print("=== 3. docker 层面三查 ===")
    run("docker ps -a --format '{{.Names}}' | grep -E 'arl_ai|mcp' || echo '[OK] 无相关容器'")
    run("docker volume ls -q | grep -E 'arl_ai' || echo '[OK] 无相关卷'")
    run("docker network ls | grep -E 'docker_arl_ai' || echo '[OK] 无相关网络'")

    print("=== 4. systemd 与端口 ===")
    run("systemctl list-unit-files | grep -E 'mcp' || echo '[OK] 无 mcp 服务单元'")
    run("ss -lnt | grep -E ':5004|:5005|:8010|:8011|:27019' || echo '[OK] 端口全释放'")

    print("=== 5. 原灯塔与无关项目完好性 ===")
    run("docker ps --format '{{.Names}}\\t{{.Status}}' | grep -E '^arl_|^arl_'")
    run("curl -sk -o /dev/null -w '原灯塔5003: %{http_code}\\n' https://127.0.0.1:5003/")
    run("ls /opt/docker_arl/config-docker.yaml /opt/docker_arl/docker-compose.yml "
        "&& echo '[OK] 原灯塔部署目录完好'")
    c.close()


if __name__ == "__main__":
    main()
