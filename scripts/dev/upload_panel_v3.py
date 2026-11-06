"""上传竖排菜单兼容版 mcp_panel.js，index.html 缓存版本 bump 到 v3。"""

import os

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(ROOT, "scripts", "deploy")
ARD = "/opt/docker_arl_ai"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    sftp = c.open_sftp()
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    html = html.replace("mcp_panel.js?v=2", "mcp_panel.js?v=3")
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")
    sftp.close()
    print("面板 JS 已更新（竖排菜单兼容），index 缓存 v=3")
    c.close()


if __name__ == "__main__":
    main()
