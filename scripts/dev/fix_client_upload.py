"""修复部署：上传修好的 arl_client.py，重启 mcp-ai，验证管理 API 与主端点。"""

import base64
import os
import sys
import time

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(ROOT, "arl_mcp", "arl_client.py")
REMOTE_DIR = "/root/ARL-AI/arl_mcp"
REMOTE = REMOTE_DIR + "/arl_client.py"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd, timeout=120, fatal=True):
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        if o.strip():
            print(o.strip()[-1000:])
        if e.strip():
            print("[stderr]", e.strip()[-400:])
        if rc != 0 and fatal:
            raise SystemExit(f"rc={rc}: {cmd}")
        return o

    # 1. 确保目录存在
    run(f"mkdir -p {REMOTE_DIR} && ls {REMOTE_DIR} | head -8")

    # 2. SFTP 上传（重试 3 次，失败走 base64+exec 兜底）
    ok = False
    for attempt in range(1, 4):
        try:
            sftp = c.open_sftp()
            sftp.put(LOCAL, REMOTE)
            sftp.close()
            st_size = None
            print(f"SFTP 上传成功 (第 {attempt} 次尝试)")
            ok = True
            break
        except Exception as e:
            print(f"SFTP 第 {attempt} 次失败: {e}")
            time.sleep(2)
    if not ok:
        data = base64.b64encode(open(LOCAL, "rb").read()).decode()
        run(f"base64 -d > {REMOTE} <<'B64EOF'\n{data}\nB64EOF")
        print("已用 base64 兜底上传")

    # 3. 校验内容
    run(f"md5sum {REMOTE} | head -1; head -3 {REMOTE}")

    # 4. 重启服务并验证
    run("systemctl restart mcp-ai.service && sleep 5 && systemctl is-active mcp-ai")
    run("journalctl -u mcp-ai -n 12 --no-pager | tail -8")
    run("curl -s http://127.0.0.1:8000/admin/config && echo ' <- 直连 :8000'")
    run("curl -sk https://127.0.0.1:5004/mcp_admin/config && echo ' <- 经 nginx 代理'")
    run("curl -sk -o /dev/null -w 'web %{http_code}\\n' https://127.0.0.1:5004/")
    c.close()


if __name__ == "__main__":
    main()
