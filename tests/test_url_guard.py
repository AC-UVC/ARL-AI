"""SSRF 防护测试：工具参数 URL 出网前必须被拦截私有/保留地址。"""

import pytest

from arl_mcp import url_guard
from arl_mcp.url_guard import UrlBlocked, validate_url

BLOCKED = [
    "ftp://example.com/x",                       # 非 http/https
    "file:///etc/passwd",                        # 本地协议
    "http:///no-host",                           # 缺主机名
    "http://localhost/x",
    "http://LOCALHOST:5003/x",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://127.0.0.1:5003/",
    "http://10.1.2.3/admin",
    "http://172.16.0.9/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",  # 云元数据
    "http://100.64.0.1/",
    "http://0.0.0.0/",
    "http://224.0.0.1/",
    "http://[::1]/",
    "http://[fe80::1]/",
]

ALLOWED = [
    "http://93.184.216.34/",     # 公网 IP 字面量
    "https://example.com/path",  # 公网域名（跳过 DNS 的场景）
]


@pytest.mark.parametrize("url", BLOCKED)
def test_blocked(url):
    with pytest.raises(UrlBlocked):
        validate_url(url, resolve_dns=False)


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed(url):
    assert validate_url(url, resolve_dns=False) == url


def test_dns_rebinding_intercepted(monkeypatch):
    # 域名看着是公网，解析出来是内网 → 必须拦
    def fake_resolver(host, port):
        return [(None, None, None, "", ("10.0.0.5", port))]
    monkeypatch.setattr(url_guard, "_resolver", fake_resolver)
    with pytest.raises(UrlBlocked):
        validate_url("http://evil.example.com/")


def test_dns_resolves_public_ok(monkeypatch):
    def fake_resolver(host, port):
        return [(None, None, None, "", ("8.8.8.8", port))]
    monkeypatch.setattr(url_guard, "_resolver", fake_resolver)
    assert validate_url("http://ok.example.com/") == "http://ok.example.com/"


def test_dns_failure_blocked(monkeypatch):
    def broken_resolver(host, port):
        raise OSError("dns down")
    monkeypatch.setattr(url_guard, "_resolver", broken_resolver)
    with pytest.raises(UrlBlocked):
        validate_url("http://ok.example.com/")
