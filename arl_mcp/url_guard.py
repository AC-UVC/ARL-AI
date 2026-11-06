"""SSRF 防护：工具参数里给出的 URL，出网前必须通过这里。

策略（Mimosa 生成前安全约束）：
- 仅允许 http / https；
- 拒绝 localhost、环回、私有、保留、链路本地、组播等地址；
- 域名会做 DNS 解析并逐一校验解析结果（防 DNS Rebinding）。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# 明确禁止的主机名（含各大云的元数据端点）
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
}

ALLOWED_SCHEMES = ("http", "https")


class UrlBlocked(ValueError):
    """URL 未通过出网校验。"""


# CGNAT（运营商级 NAT）不在 Python is_private 判定里，必须显式拦
CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _ip_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # 解析不出合法 IP 一律视为可疑
    return (
        not addr.is_global  # 私有/环回/保留/链路本地/文档段等非公网地址全部拦截
        or addr.is_multicast
        or addr.is_unspecified
        or addr in CGNAT
    )


def _resolver(host: str, port: int):
    return socket.getaddrinfo(host, port)


def validate_url(url: str, *, resolve_dns: bool = True) -> str:
    """校验一个「数据驱动」的 URL，返回原字符串；不通过则抛 UrlBlocked。

    resolve_dns=False 时跳过 DNS 解析（用于可信部署配置或离线测试）。
    """
    if not url or not url.strip():
        raise UrlBlocked("URL 为空")
    pr = urlparse(url.strip())

    if pr.scheme not in ALLOWED_SCHEMES:
        raise UrlBlocked(f"仅允许 http/https，收到: {pr.scheme or '空'}://{url}")
    host = pr.hostname
    if not host:
        raise UrlBlocked(f"URL 缺少主机名: {url}")
    if host.lower() in BLOCKED_HOSTNAMES:
        raise UrlBlocked(f"禁止访问 {host}")

    # IP 字面量直接判；域名则解析出所有 IP 逐一判
    try:
        ipaddress.ip_address(host)
        literal = host
    except ValueError:
        literal = None

    if literal is not None:
        if _ip_blocked(literal):
            raise UrlBlocked(f"禁止访问私有/环回/保留地址: {host}")
    elif resolve_dns:
        port = pr.port or (443 if pr.scheme == "https" else 80)
        try:
            infos = _resolver(host, port)
        except OSError as e:
            raise UrlBlocked(f"域名解析失败: {host} ({e})")
        for info in infos:
            if _ip_blocked(info[4][0]):
                raise UrlBlocked(f"{host} 解析到私有/保留地址，已拦截")
    return url
