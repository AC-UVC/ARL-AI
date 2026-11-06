"""运行配置：全部来自环境变量，代码内不写死任何敏感信息。"""

import os
from pathlib import Path

# ARL 服务端地址（部署配置的可信上游，通常为 docker 里的 ARL）
ARL_URL = os.environ.get("ARL_URL", "http://127.0.0.1:5003").rstrip("/")

# 认证：优先用固定 Token（ARL config.yaml 里配的 ARL.API_KEY 也可直接当 Token 用）；
# 没有则用账号密码自动登录。ARL 默认 admin/arlpass。
ARL_TOKEN = os.environ.get("ARL_TOKEN", "")
ARL_USER = os.environ.get("ARL_USER", "admin")
ARL_PASS = os.environ.get("ARL_PASS", "arlpass")

ARL_TIMEOUT = float(os.environ.get("ARL_TIMEOUT", "30"))
ARL_TLS_VERIFY = os.environ.get("ARL_TLS_VERIFY", "0") in ("1", "true", "True")

# 严格模式：开启后连 ARL_URL 也走完整 SSRF 校验（拒绝内网/localhost）。
# 默认关闭，因为 ARL 通常就部署在 127.0.0.1。
ARL_STRICT_URL_GUARD = os.environ.get("ARL_MCP_STRICT_URL_GUARD", "0") in ("1", "true", "True")


def workspace_root() -> Path:
    """文件沙箱根目录：所有文件操作和临时文件只允许在这里面。"""
    return Path(os.environ.get("ARL_MCP_WORKSPACE") or os.getcwd()).resolve()
