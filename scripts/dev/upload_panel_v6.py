"""上传 mcp_panel.js 并 bump index 缓存版本。用法: python upload_panel_v6.py [版本号]"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY = os.path.join(ROOT, "scripts", "deploy")
ARD = "/opt/docker_arl_ai"


def main() -> None:
    ver = sys.argv[1] if len(sys.argv) > 1 else "6"
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)
    sftp = c.open_sftp()
    sftp.put(os.path.join(DEPLOY, "mcp_panel.js"), f"{ARD}/frontend/mcp_panel.js")
    idx_local = os.path.join(ROOT, ".tmp", "arl_index.html")
    sftp.get(f"{ARD}/frontend/index.html", idx_local)
    html = open(idx_local, encoding="utf-8").read()
    import re
    html = re.sub(r"mcp_panel\.js\?v=\d+", f"mcp_panel.js?v={ver}", html)
    open(idx_local, "w", encoding="utf-8").write(html)
    sftp.put(idx_local, f"{ARD}/frontend/index.html")
    sftp.close()
    print(f"面板已上传，index v{ver}")
    c.close()


if __name__ == "__main__":
    main()
