"""把 arl_mcp 包和测试脚本上传到 Kali /root/ARL-AI 并装好运行环境。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 工作目录
REMOTE = "/root/ARL-AI"

FILES = [
    ("arl_mcp/__init__.py", f"{REMOTE}/arl_mcp/__init__.py"),
    ("arl_mcp/config.py", f"{REMOTE}/arl_mcp/config.py"),
    ("arl_mcp/fs_sandbox.py", f"{REMOTE}/arl_mcp/fs_sandbox.py"),
    ("arl_mcp/url_guard.py", f"{REMOTE}/arl_mcp/url_guard.py"),
    ("arl_mcp/arl_client.py", f"{REMOTE}/arl_mcp/arl_client.py"),
    ("arl_mcp/server.py", f"{REMOTE}/arl_mcp/server.py"),
    ("arl_mcp/__main__.py", f"{REMOTE}/arl_mcp/__main__.py"),
    ("scripts/smoke_stdio.py", f"{REMOTE}/scripts/smoke_stdio.py"),
    ("scripts/mcp_data_test.py", f"{REMOTE}/scripts/mcp_data_test.py"),
]


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
        if o.strip():
            print(o.strip())
        if e.strip():
            print("[stderr]", e.strip()[-800:])
        if rc != 0:
            raise SystemExit(f"命令失败 rc={rc}: {cmd}")
        return o

    run(f"mkdir -p {REMOTE}/arl_mcp {REMOTE}/scripts")

    sftp = c.open_sftp()
    for local_rel, remote in FILES:
        sftp.put(os.path.join(ROOT, local_rel), remote)
    sftp.close()
    print(f"已上传 {len(FILES)} 个文件到 {REMOTE}")

    # venv + 依赖（清华源）
    run("python3 -m venv /root/ARL-AI/.venv", timeout=120)
    run("/root/ARL-AI/.venv/bin/pip install -q --upgrade pip "
        "-i https://pypi.tuna.tsinghua.edu.cn/simple", timeout=180)
    run("/root/ARL-AI/.venv/bin/pip install -q mcp httpx "
        "-i https://pypi.tuna.tsinghua.edu.cn/simple", timeout=600)

    run("/root/ARL-AI/.venv/bin/python -c 'import mcp, httpx; print(\"kali 依赖 ok\")'")
    c.close()
    print("Kali MCP 环境就绪")


if __name__ == "__main__":
    main()
