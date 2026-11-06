"""Kali 部署辅助：SFTP 上传文件。python sftp_put.py 本地文件 /远程/路径"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, 22, username="root", password="kali", timeout=8,
          allow_agent=False, look_for_keys=False)
sftp = c.open_sftp()
sftp.put(sys.argv[1], sys.argv[2])
st = sftp.stat(sys.argv[2])
print(f"已上传 {sys.argv[1]} -> {sys.argv[2]} ({st.st_size} bytes)")
sftp.close()
c.close()
