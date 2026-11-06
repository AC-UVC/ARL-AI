"""Kali SSH 执行器：python ssh_kali.py "命令"  （凭据从环境变量或默认列表尝试）"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
CANDIDATES = [
    ("root", "kali"),
    ("kali", "kali"),
    ("root", "toor"),
    ("root", "root"),
]
if os.environ.get("KALI_USER"):
    CANDIDATES.insert(0, (os.environ["KALI_USER"], os.environ.get("KALI_PASS", "")))


def connect() -> tuple[paramiko.SSHClient, str]:
    last_err = None
    for user, pwd in CANDIDATES:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(HOST, 22, username=user, password=pwd, timeout=8,
                      allow_agent=False, look_for_keys=False)
            return c, user
        except paramiko.AuthenticationException:
            last_err = f"认证失败 {user}/{pwd}"
        except Exception as e:  # 网络错误直接报
            raise SystemExit(f"连接失败 {HOST}: {e}")
    raise SystemExit(f"所有默认凭据都失败: {last_err}；请设置 KALI_USER/KALI_PASS")


def main() -> None:
    c, user = connect()
    try:
        _, out, err = c.exec_command(sys.argv[1], timeout=120)
        o, e = out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        if o:
            print(o, end="")
        if e:
            print("[stderr]", e, end="")
        sys.exit(rc)
    finally:
        c.close()


if __name__ == "__main__":
    main()
