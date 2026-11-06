"""上传叠加安装 assets 并在 Kali 原灯塔上真实执行 overlay_install.sh。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = {
    "overlay_install.sh": os.path.join(ROOT, "scripts", "deploy", "overlay_install.sh"),
    "mcp_service.py": os.path.join(ROOT, "scripts", "deploy", "mcp_service.py"),
    "mcp_panel.js": os.path.join(ROOT, "scripts", "deploy", "mcp_panel.js"),
    "arl_mcp/__init__.py": os.path.join(ROOT, "arl_mcp", "__init__.py"),
    "arl_mcp/config.py": os.path.join(ROOT, "arl_mcp", "config.py"),
    "arl_mcp/fs_sandbox.py": os.path.join(ROOT, "arl_mcp", "fs_sandbox.py"),
    "arl_mcp/url_guard.py": os.path.join(ROOT, "arl_mcp", "url_guard.py"),
    "arl_mcp/arl_client.py": os.path.join(ROOT, "arl_mcp", "arl_client.py"),
    "arl_mcp/server.py": os.path.join(ROOT, "arl_mcp", "server.py"),
}


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd, timeout=560, show=True):
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        if show:
            tail = o[-2600:] if len(o) > 2600 else o
            print(tail)
            if e.strip():
                print("[stderr]", e.strip()[-600:])
            print(f"[rc={rc}]")
        return rc, o

    run("mkdir -p /root/arl-overlay/arl_mcp")
    sftp = c.open_sftp()
    for rel, local in ASSETS.items():
        sftp.put(local, "/root/arl-overlay/" + rel)
    sftp.close()
    run("chmod +x /root/arl-overlay/overlay_install.sh && ls /root/arl-overlay", show=False)

    print("=== 在原灯塔上执行叠加安装 ===")
    run("bash /root/arl-overlay/overlay_install.sh "
        "--dir /opt/docker_arl --web-port 5003 --web-container arl_web "
        "--mcp-port 8010 --admin-port 8011 --arl-pass arlpass")
    c.close()


if __name__ == "__main__":
    main()
