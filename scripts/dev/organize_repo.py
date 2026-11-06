"""仓库整理：把开发/测试过程脚本归档到 scripts/dev/，部署交付物留在 scripts/deploy/。"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy"
DEV = ROOT / "scripts" / "dev"
DEV.mkdir(exist_ok=True)

# 保留在 deploy/ 的交付物
KEEP = {
    "install.sh",
    "mcp_service.py",
    "mcp_panel.js",
    "docker-compose.arl-ai.yml",
    "mcp_admin.conf",
}
moved = []
for f in sorted(DEPLOY.iterdir()):
    if f.name in KEEP or f.is_dir():
        continue
    shutil.move(str(f), str(DEV / f.name))
    moved.append(f.name)

# 散在 scripts/ 根的 Kali 工具
for name in ("ssh_kali.py", "sftp_put.py", "kali_ssh.py"):
    p = ROOT / "scripts" / name
    if p.exists():
        shutil.move(str(p), str(DEV / name))
        moved.append(name)

print(f"归档 {len(moved)} 个文件到 scripts/dev/")
print("deploy/ 现存交付物:")
for f in sorted((ROOT / "scripts" / "deploy").iterdir()):
    print("  ", f.name)
