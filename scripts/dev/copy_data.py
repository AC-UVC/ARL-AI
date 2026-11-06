"""把原灯塔（arl_mongodb）数据全量拷贝到新灯塔（arl_ai_mongodb）。

dump -> /tmp/arl_ai_test/arl_backup.archive -> restore --drop
"""

import os
import sys
import time

import paramiko

HOST = os.environ.get("KALI_HOST", "192.168.224.128")
ARCHIVE = "/tmp/arl_ai_test/arl_backup.archive"


def main() -> None:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, username="root", password="kali", timeout=8,
              allow_agent=False, look_for_keys=False)

    def run(cmd: str, timeout: int = 600) -> str:
        print(f"$ {cmd}")
        _, out, err = c.exec_command(cmd, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        rc = out.channel.recv_exit_status()
        tail_o = o if len(o) < 3000 else o[-3000:]
        print(tail_o)
        if e.strip():
            print("[stderr]", e[-1500:])
        if rc != 0:
            print(f"[rc={rc}]")
            sys.exit(rc)
        return o

    t0 = time.time()

    # 1. 原库 dump（只读操作，不动原灯塔）
    run("docker exec arl_mongodb mongodump -u admin -p admin "
        "--authenticationDatabase admin --db arl --archive --gzip "
        f"> {ARCHIVE} 2>/tmp/arl_ai_test/dump.log && ls -lh {ARCHIVE}")

    # 2. restore 到新库（--drop 保证与原库一致）
    run("docker exec -i arl_ai_mongodb mongorestore -u admin -p admin "
        "--authenticationDatabase admin --archive --gzip --drop "
        f"< {ARCHIVE} 2>&1 | tail -5")

    # 3. 两边集合计数比对
    counts_cmd = ("docker exec %s mongo -u admin -p admin --authenticationDatabase "
                  "admin arl --quiet --eval \"db.getCollectionNames().forEach("
                  "function(c){print(c, db[c].count({}))})\" 2>/dev/null")
    orig = run(counts_cmd % "arl_mongodb")
    new = run(counts_cmd % "arl_ai_mongodb")

    def parse(txt):
        d = {}
        for line in txt.splitlines():
            parts = line.rsplit(" ", 1)
            if len(parts) == 2 and parts[1].isdigit():
                d[parts[0]] = int(parts[1])
        return d

    a, b = parse(orig), parse(new)
    print(f"\n{'集合':<28}{'原库':>10}{'新库':>10}  结果")
    mismatch = 0
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k, 0), b.get(k, 0)
        ok = "✓" if va == vb else "✗ 不一致"
        if va != vb:
            mismatch += 1
        print(f"{k:<28}{va:>10}{vb:>10}  {ok}")
    print(f"\n拷贝耗时 {time.time()-t0:.0f}s，不一致集合数: {mismatch}")
    c.close()


if __name__ == "__main__":
    main()
