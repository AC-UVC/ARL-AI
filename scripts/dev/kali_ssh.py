"""Kali SSH 助手：paramiko 非交互执行远程命令。

用法: python kali_ssh.py "<远程命令>"
凭据从 KALI_USER/KALI_PASS 环境变量读，或依次尝试常见口令。
"""

import os
import sys

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
CREDS = [
    ("root", "kali"),
    ("kali", "kali"),
    ("root", "toor"),
    ("root", "root"),
    ("root", "123456"),
]


def connect():
    user = os.environ.get("KALI_USER")
    pw = os.environ.get("KALI_PASS")
    pairs = [(user, pw)] if user and pw else CREDS
    last_err = None
    for u, p in pairs:
        try:
            cli = paramiko.SSHClient()
            cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            cli.connect(HOST, 22, u, p, timeout=8, allow_agent=False,
                        look_for_keys=False)
            print(f"[ssh] {u}@{HOST} 登录成功", file=sys.stderr)
            return cli
        except paramiko.AuthenticationException:
            last_err = f"{u}: 认证失败"
        except Exception as e:
            last_err = f"{u}: {e}"
    raise SystemExit(f"SSH 连接失败: {last_err}")


def run(cli, cmd, timeout=300):
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "id; hostname"
    cli = connect()
    code, out, err = run(cli, cmd)
    sys.stdout.write(out)
    if err.strip():
        sys.stderr.write("[stderr] " + err)
    cli.close()
    sys.exit(code)
