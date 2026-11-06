"""一键安装脚本的真实安装测试准备：上传 assets 到 Kali /root/arl-install/。

目录结构（install.sh 的运行前提）：
  /root/arl-install/
  ├── install.sh
  ├── mcp_service.py
  ├── mcp_panel.js
  └── arl_mcp/*.py
"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = {
    "install.sh": os.path.join(ROOT, "scripts", "deploy", "install.sh"),
    "mcp_service.py": os.path.join(ROOT, "scripts", "deploy", "mcp_service.py"),
    "mcp_panel.js": os.path.join(ROOT, "scripts", "deploy", "mcp_panel.js"),
    "arl_mcp/__init__.py": os.path.join(ROOT, "arl_mcp", "__init__.py"),
    "arl_mcp/config.py": os.path.join(ROOT, "arl_mcp", "config.py"),
    "arl_mcp/fs_sandbox.py": os.path.join(ROOT, "arl_mcp", "fs_sandbox.py"),
    "arl_mcp/url_guard.py": os.path.join(ROOT, "arl_mcp", "url_guard.py"),
    "arl_tep/__init__.py": None,  # 占位，跳过
    "arl_mcp/arl_client.py": os.path.join(ROOT, "arl_mcp", "arl_client.py"),
    "arl_mcp/server.py": os.path.join(ROOT, "arl_mcp", "server.py"),
    "arl_mcp/__main__.py": None,  # 占位，跳过
}


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
            print(o.strip()[-500:])
        if e.strip():
            print("[stderr]", e.strip()[-300:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    run("mkdir -p /root/arl-install/arl_mcp")
    sftp = c.open_sftp()
    n = 0
    for rel, local in LOCAL.items():
        if local is None:
            continue
        sftp.put(local, "/root/arl-install/" + rel)
        n += 1
    sftp.close()
    run("chmod +x /root/arl-install/install.sh && ls /root/arl-install")
    c.close()
    print(f"已上传 {n} 个文件到 /root/arl-install/")


if __name__ == "__main__":
    main()
