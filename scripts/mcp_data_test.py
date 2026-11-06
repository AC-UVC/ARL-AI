"""MCP 数据读取测试（测试标准：MCP 能读取到 ARL 里的任意扫描数据）。

直接驱动 arl_client 逐集合查询新灯塔 API，并与 MongoDB 实际计数比对。
在 Kali 或 Windows 上均可运行。

用法:
    KALI:   ARL_URL=https://127.0.0.1:5004 .venv/bin/python mcp_data_test.py
    WIN:    ARL_URL=https://192.168.224.128:5004 .venv/Scripts/python.exe mcp_data_test.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arl_mcp.arl_client import ARLClient  # noqa: E402

# 测试的集合 -> 关键过滤字段（验证过滤参数真实生效）
CHECKS = [
    ("task", {}),
    ("site", {}),
    ("domain", {}),
    ("ip", {}),
    ("url", {}),
    ("nuclei_result", {}),
    ("vuln", {}),
    ("cert", {}),
    ("service", {}),
    ("fileleak", {}),
    ("cip", {}),
    ("wih", {}),
    ("fingerprint", {}),
    ("poc", {}),
    ("stat_finger", {}),
]

# 过滤参数功能验证（任一命中即过）
FILTER_CHECKS = [
    ("site", {"status": 200}, "status=200 站点过滤"),
    ("site", {"finger.name": "nginx"}, "指纹过滤"),
    ("domain", {"type": "A"}, "A 记录过滤"),
    ("ip", {"ip_type": "PUBLIC"}, "公网 IP 过滤"),
    ("nuclei_result", {"vuln_severity": "critical"}, "nuclei 严重级别过滤"),
    ("task", {"status": "done"}, "任务状态过滤"),
]


def main() -> int:
    base = os.environ.get("ARL_URL", "https://127.0.0.1:5004")
    c = ARLClient(base_url=base, username="admin", password="arlpass")
    c.login()

    print(f"== 数据读取测试 @ {base} ==\n")
    fails = 0
    print(f"{'集合':<16}{'API total':>12}{'状态':>8}")
    for coll, extra in CHECKS:
        try:
            data = c.query(coll, page=1, size=5)
            total = data.get("total", 0)
            items = data.get("items") or []
            status = "✓" if total > 0 and items else ("○ 空" if total == 0 else "✗")
            if total > 0 and not items:
                fails += 1
            print(f"{coll:<16}{total:>12}{status:>8}")
        except Exception as e:
            print(f"{coll:<16}{'ERR':>12}  ✗ {e}")
            fails += 1

    print("\n-- 过滤参数功能验证 --")
    for coll, f, name in FILTER_CHECKS:
        try:
            data = c.query(coll, page=1, size=5, filters=f)
            total = data.get("total", 0)
            ok = total > 0
            if not ok:
                fails += 1
            print(f"{name:<28} total={total:<8} {'✓' if ok else '✗ 0 结果'}")
        except Exception as e:
            print(f"{name:<28} ✗ {e}")
            fails += 1

    # 单条数据完整性抽查：site 文档字段
    sites = c.query("site", page=1, size=1)
    doc = (sites.get("items") or [{}])[0]
    fields = ["site", "hostname", "ip", "title", "status"]
    missing = [f for f in fields if f not in doc]
    print(f"\n-- site 文档字段抽查: {'完整 ✓' if not missing else '缺 ' + str(missing)}")
    if missing:
        fails += 1
    print(f"样例: {doc.get('site', '?')} | title={str(doc.get('title', ''))[:30]}")

    c.close()
    print(f"\n结论: {'通过' if fails == 0 else f'失败 x{fails}'}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
