"""收工清理：删除 Kali 测试灯塔（docker_arl_ai 项目）+ MCP 服务 + 数据，原灯塔不动。

清理项：
1. mcp-ai.service（systemd 停止+禁用+删文件）
2. /opt/docker_arl_ai（compose down -v：容器+卷=全部测试数据；删目录）
3. /root/ARL-AI（MCP 代码+venv+状态文件）
4. 验证：arl_ai_* 容器/卷/网络清零、端口释放、原灯塔 arl_* 正常
"""

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
        print(f"$ {cmd[:80]}\n{o.strip()[-500:]}")
        if e.strip():
            print("[stderr]", e.strip()[-300:])
        return rc

    print("=== 1. 停止并删除 MCP 服务 ===")
    run("systemctl disable --now mcp-ai 2>/dev/null; "
        "rm -f /etc/systemd/system/mcp-ai.service; systemctl daemon-reload; "
        "systemctl is-active mcp-ai || echo 'mcp-ai 服务已移除'")

    print("=== 2. 删除测试灯塔容器组（含数据卷）===")
    run("cd /opt/docker_arl_ai && docker compose down -v", timeout=420)

    print("=== 3. 删除部署目录与 MCP 代码 ===")
    run("rm -rf /opt/docker_arl_ai /root/ARL-AI /root/arl-install")

    print("=== 4. 清理验证 ===")
    run("docker ps -a --format '{{.Names}}' | grep arl_ai || echo '[OK] arl_ai 容器清零'")
    run("docker volume ls -q | grep arl_ai || echo '[OK] arl_ai 卷清零'")
    run("docker network ls -q | grep docker_arl_ai || echo '[OK] arl_ai 网络清零'")
    run("ss -lnt | grep -E ':5004|:5005|:8010|:8011|:27019' || echo '[OK] 端口已释放'")
    run("ls /opt/docker_arl_ai /root/ARL-AI 2>&1 | grep -c 'No such' && echo '[OK] 目录已删除'")

    print("=== 5. 原灯塔完好性确认（未动）===")
    run("docker ps --format '{{.Names}}\\t{{.Status}}' | grep -E 'arl_web|arl_worker|arl_scheduler|arl_mongodb|arl_rabbitmq'")
    run("curl -sk -o /dev/null -w '原灯塔 5003: %{http_code}\\n' https://127.0.0.1:5003/")
    run("ls /opt/docker_arl | head -5")
    c.close()


if __name__ == "__main__":
    main()
