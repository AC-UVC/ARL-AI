"""MCP HTTP 服务：数据面 + 管理面分离。

- 数据面: FastMCP streamable-http，监听 0.0.0.0:<用户可选端口>，
  强制请求头鉴权（X-API-Key 或 Authorization: Bearer），支持服务开关。
- 管理面: 固定 127.0.0.1:8011（灯塔 nginx 同源代理给 UI 面板），
  提供开关/密钥重置/IP 选择/端口修改（修改后延迟自重启生效），
  以及灯塔全局配置辅助编辑（config.yaml：FOFA/GitHub/钉钉/飞书/企微等，
  白名单字段 + 掩码回显 + 多容器同写 + 重启生效）。

状态存 JSON 文件（MongoDB 4.0 与新 pymongo 不兼容，文件状态最稳）。
"""

import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time as _time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from arl_mcp.server import mcp  # noqa: F401  工具已全部注册的 FastMCP 实例

STATE_PATH = os.environ.get(
    "MCP_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_config.json"))
ADMIN_PORT = int(os.environ.get("MCP_ADMIN_PORT", "8011"))
DEFAULT_PORT = int(os.environ.get("MCP_PORT", "8010"))
SERVICE_NAME = os.environ.get("MCP_SERVICE_NAME", "mcp-ai")
_ips_cache = {"t": 0.0, "v": None}

_lock = threading.Lock()


# ---------------------------------------------------------------- 状态

def _load() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(cfg: dict) -> None:
    with _lock:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        os.replace(tmp, STATE_PATH)


def get_cfg() -> dict:
    cfg = _load()
    cfg.pop("token", None)  # v1 遗留字段清理
    changed = False
    if "api_key" not in cfg or not cfg["api_key"]:
        cfg["api_key"] = secrets.token_hex(24)  # 调用密钥：必存在，运行时生成
        changed = True
    cfg.setdefault("enabled", False)
    if "port" not in cfg:
        cfg["port"] = DEFAULT_PORT
        changed = True
    if "ip" not in cfg or not cfg["ip"] or cfg["ip"].startswith("127."):
        # 默认当前主 IP；无外网环境 default_ip 可能回退 127.x，优先取网卡地址
        ip = default_ip()
        if ip.startswith("127."):
            nic = [i for i in all_ips() if not i.startswith("127.")]
            ip = nic[0] if nic else ip
        if cfg.get("ip") != ip:
            cfg["ip"] = ip
            changed = True
    if changed:
        _save(cfg)
    return cfg


def set_cfg(**kw) -> dict:
    cfg = get_cfg()
    cfg.update(kw)
    _save(cfg)
    return cfg


# ---------------------------------------------------------------- IP 枚举

def _port_free(port: int) -> bool:
    """预检端口可绑定，防止改到被占端口后服务进入重启死循环。"""
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _schedule_restart() -> None:
    """延迟自重启使新端口生效：优先 systemd；无 systemd 时 exec 自替换。"""
    import shutil
    import sys

    def _systemd():
        subprocess.run(["systemctl", "restart", SERVICE_NAME],
                       check=False)

    def _exec_self():
        os.execv(sys.executable, [sys.executable] + sys.argv)

    if shutil.which("systemctl"):
        threading.Timer(0.5, _systemd).start()
    else:
        threading.Timer(0.5, _exec_self).start()


def default_ip() -> str:
    """主出口 IP（UDP connect 探测，不真正发包）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def all_ips() -> list:
    """可选地址：公网 IP（MCP_PUBLIC_IP 配置）+ 各网卡 IP + 回环。
    结果缓存 60s，避免慢 DNS（gethostbyname_ex）阻塞每个管理请求。"""
    now = _time.time()
    if not _ips_cache["v"] or now - _ips_cache["t"] > 60:
        _ips_cache["v"] = _compute_ips()
        _ips_cache["t"] = now
    return list(_ips_cache["v"])


def _compute_ips() -> list:
    ips = []
    pub = os.environ.get("MCP_PUBLIC_IP", "").strip()
    if pub:
        ips.append(pub)
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip in ips or (ip.startswith("127.") and ip != "127.0.0.1"):
                continue  # 去重 + 跳过 /etc/hosts 的 127.x 别名
            ips.append(ip)
    except Exception:
        pass
    main = default_ip()
    if main not in ips:
        ips.insert(0, main)
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return ips


# ---------------------------------------------------------------- 灯塔全局配置
# 辅助编辑灯塔 config.yaml（FOFA/GitHub/钉钉/飞书/企微/邮件/代理/第三方测绘插件）。
# 存储在每个灯塔容器内 /code/app/config.yaml，进程启动时读一次 → 保存后需重启容器生效。
# 安全边界：字段白名单（绝不触碰 MONGO/CELERY/ARL.AUTH 等敏感段）、
# 掩码回显（含 *** 的提交值视为未修改不覆盖）、多容器同写。

ARL_CONFIG_PATH = "/code/app/config.yaml"
_cfg_containers_cache = {"t": 0.0, "v": []}
_arl_view_cache = {"t": 0.0, "v": None}   # 配置视图 30s 缓存（读一次 docker exec 要 1-3s）

# 可编辑字段（点路径）+ 是否敏感（敏感值回显掩码）
ARL_CONFIG_FIELDS = [
    ("FOFA.EMAIL", False, "FOFA Email"),
    ("FOFA.KEY", True, "FOFA Key"),
    ("FOFA.URL", False, "FOFA 接口地址（中转站填其 baseurl）"),
    ("GITHUB.TOKEN", True, "GitHub Token（PAT，解除监控 API 限流）"),
    ("DINGDING.ACCESS_TOKEN", True, "钉钉机器人 AccessToken"),
    ("DINGDING.SECRET", True, "钉钉加签 Secret（与 AccessToken 缺一不可）"),
    ("FEISHU.WEBHOOK_URL", True, "飞书机器人 Webhook"),
    ("FEISHU.SECRET", True, "飞书加签 Secret"),
    ("WXWORK.WEBHOOK_URL", True, "企业微信机器人 Webhook（仅此一项即可用）"),
    ("WEBHOOK.URL", True, "自定义 Webhook URL"),
    ("WEBHOOK.TOKEN", True, "自定义 Webhook Token"),
    ("PROXY.HTTP_URL", False, "扫描代理（http://host:port）"),
    ("EMAIL.HOST", False, "邮件 SMTP 主机"),
    ("EMAIL.PORT", False, "邮件 SMTP 端口"),
    ("EMAIL.USERNAME", False, "邮件用户名"),
    ("EMAIL.PASSWORD", True, "邮件密码/授权码"),
    ("EMAIL.TO", False, "通知收件人"),
]
# QUERY_PLUGIN 内允许编辑的叶子字段
_PLUGIN_FIELDS = {"api_key", "auth_email", "auth_key", "quake_token",
                  "enable", "page_size", "max_page", "max_size", "after_id"}
_PLUGIN_SENSITIVE = {"api_key", "auth_key", "quake_token"}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "****"
    return value[:4] + "****" + value[-4:]


def _config_containers() -> list:
    """所有带 /code/app/config.yaml 的运行中容器（60s 缓存）。"""
    now = _time.time()
    if _cfg_containers_cache["v"] and now - _cfg_containers_cache["t"] < 60:
        return list(_cfg_containers_cache["v"])
    try:
        names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                               capture_output=True, text=True,
                               timeout=15).stdout.split()
    except Exception:
        names = []
    out = []
    for n in names:
        try:
            r = subprocess.run(["docker", "exec", n, "test", "-f",
                                ARL_CONFIG_PATH],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                out.append(n)
        except Exception:
            pass
    _cfg_containers_cache["t"] = now
    _cfg_containers_cache["v"] = out
    return list(out)


def _load_arl_yaml():
    """从第一个配置容器读 config.yaml → dict；失败抛 RuntimeError。"""
    cs = _config_containers()
    if not cs:
        raise RuntimeError("未找到含 config.yaml 的灯塔容器（docker ps 检查）")
    r = subprocess.run(
        ["docker", "exec", cs[0], "python3", "-c",
         "import yaml,json;print(json.dumps(yaml.safe_load(open('%s'))))"
         % ARL_CONFIG_PATH],
        capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError("读取 config.yaml 失败: " + r.stderr[-200:])
    return json.loads(r.stdout)


def _set_by_path(y: dict, path: str, value) -> None:
    cur = y
    parts = path.split(".")
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur or \
                not isinstance(cur[p], dict):
            raise RuntimeError("配置路径不存在: " + path)
        cur = cur[p]
    leaf = parts[-1]
    if not isinstance(cur, dict) or leaf not in cur:
        raise RuntimeError("配置路径不存在: " + path)
    old = cur[leaf]
    if isinstance(old, bool) or isinstance(value, bool):
        if not isinstance(value, bool):
            value = str(value).strip().lower() in ("true", "1", "yes", "on")
    elif isinstance(old, int) and not isinstance(old, bool):
        value = int(str(value).strip())
    cur[leaf] = value


def _dump_arl_yaml(container: str, y: dict) -> None:
    payload = json.dumps(y, ensure_ascii=False)
    r = subprocess.run(
        ["docker", "exec", "-i", container, "python3", "-c",
         "import sys,yaml,json;y=json.load(sys.stdin);"
         "open('%s','w').write(yaml.safe_dump(y,allow_unicode=True,"
         "sort_keys=False,default_flow_style=False))" % ARL_CONFIG_PATH],
        input=payload, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"写回 {container} 失败: " + r.stderr[-200:])


def arl_config_view() -> dict:
    """GET：返回掩码后的字段值 + 配置容器清单（30s 缓存，保存/重启即失效）。"""
    now = _time.time()
    if _arl_view_cache["v"] is not None and now - _arl_view_cache["t"] < 30:
        return _arl_view_cache["v"]
    y = _load_arl_yaml()
    fields = []
    for path, sensitive, label in ARL_CONFIG_FIELDS:
        cur = y
        ok = True
        for p in path.split("."):
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        val = cur if ok else ""
        fields.append({"path": path, "label": label, "sensitive": sensitive,
                       "value": _mask(str(val)) if sensitive else str(val)})
    plugins = []
    for name, conf in (y.get("QUERY_PLUGIN") or {}).items():
        if not isinstance(conf, dict):
            continue
        sub = []
        for k, v in conf.items():
            if k not in _PLUGIN_FIELDS:
                continue
            sub.append({"key": k, "label": k,
                        "sensitive": k in _PLUGIN_SENSITIVE,
                        "value": _mask(str(v)) if k in _PLUGIN_SENSITIVE
                        else str(v)})
        if sub:
            plugins.append({"name": name, "fields": sub})
    view = {"containers": _config_containers(), "fields": fields,
            "plugins": plugins}
    _arl_view_cache["t"] = now
    _arl_view_cache["v"] = view
    return view


def arl_config_save(values: dict) -> dict:
    """POST save：白名单校验 → 跳过掩码值 → 三个容器同写。"""
    y = _load_arl_yaml()
    allowed = {p for p, _, _ in ARL_CONFIG_FIELDS}
    for name, conf in (y.get("QUERY_PLUGIN") or {}).items():
        if isinstance(conf, dict):
            for k in conf:
                if k in _PLUGIN_FIELDS:
                    allowed.add(f"QUERY_PLUGIN.{name}.{k}")
    applied, skipped = [], []
    for path, value in (values or {}).items():
        if path not in allowed:
            return {"error": "字段不在白名单: " + path}
        sv = str(value)
        if "***" in sv:
            skipped.append(path)          # 掩码值 = 用户未改，不覆盖
            continue
        _set_by_path(y, path, sv)
        applied.append(path)
    if applied:
        for c in _config_containers():
            _dump_arl_yaml(c, y)
        _arl_view_cache["t"] = 0          # 保存后视图缓存失效
        _arl_view_cache["v"] = None
    return {"ok": True, "applied": applied, "skipped": skipped,
            "note": "已写回全部配置容器；需重启容器生效"}


def _restart_config_containers_async():
    cs = _config_containers()
    order = [c for c in cs if "scheduler" in c] + \
            [c for c in cs if "worker" in c] + \
            [c for c in cs if c not in
             [x for x in cs if "scheduler" in x]
             and c not in [x for x in cs if "worker" in x]]

    def work():
        for c in order:
            try:
                subprocess.run(["docker", "restart", c],
                               capture_output=True, timeout=180)
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()
    return order


# ---------------------------------------------------------------- 数据面守卫

class ApiKeyGuard(BaseHTTPMiddleware):
    """/mcp 主端点守卫：服务开关 + 强制请求头密钥（X-API-Key / Bearer）。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            cfg = get_cfg()
            if not cfg.get("enabled"):
                return JSONResponse(
                    {"error": "MCP 服务已关闭，请在灯塔 UI 的 MCP 栏目里开启"},
                    status_code=403)
            key = request.headers.get("x-api-key")
            auth = request.headers.get("authorization", "")
            if not key and auth.lower().startswith("bearer "):
                key = auth[7:].strip()
            if not key:
                return JSONResponse(
                    {"error": "缺少 X-API-Key 请求头"}, status_code=401)
            if key != cfg.get("api_key"):
                return JSONResponse({"error": "API 密钥无效"}, status_code=401)
        return await call_next(request)


app = mcp.streamable_http_app()
app.add_middleware(ApiKeyGuard)


# ---------------------------------------------------------------- 管理面

class AdminHandler(BaseHTTPRequestHandler):
    def _source_allowed(self) -> bool:
        """管理面来源白名单：默认本机 + 全部私有网段（nginx 容器经网桥访问宿主
        的源地址因部署而异，可用 MCP_ADMIN_ALLOW 覆盖，逗号分隔前缀）。"""
        allowed = os.environ.get("MCP_ADMIN_ALLOW", "")
        prefixes = ([p.strip() for p in allowed.split(",") if p.strip()]
                    or ["127.", "10.", "172.", "192.168."])
        ip = self.client_address[0]
        return any(ip.startswith(p) for p in prefixes)

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        cfg = get_cfg()
        return {"enabled": bool(cfg["enabled"]), "api_key": cfg["api_key"],
                "port": int(cfg["port"]), "ip": cfg["ip"],
                "ips": all_ips(), "admin_port": ADMIN_PORT}

    def do_GET(self):
        if not self._source_allowed():
            return self._send({"error": "forbidden"}, 403)
        p = self.path.split("?")[0].rstrip("/")
        if p in ("/admin/config", ""):
            self._send(self._payload())
        elif p == "/admin/arlconfig":
            try:
                self._send(arl_config_view())
            except Exception as e:
                self._send({"error": str(e)}, 500)
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        if not self._source_allowed():
            return self._send({"error": "forbidden"}, 403)
        p = self.path.split("?")[0].rstrip("/")
        if p == "/admin/arlconfig":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                body = {}
            action = body.get("action")
            try:
                if action == "save":
                    return self._send(arl_config_save(body.get("values")))
                if action == "restart":
                    order = _restart_config_containers_async()
                    _arl_view_cache["t"] = 0      # 容器清单将变化，缓存失效
                    _arl_view_cache["v"] = None
                    return self._send({"ok": True, "restarting": order,
                                       "note": "重启中（web 约 30 秒不可访问）"})
            except RuntimeError as e:
                return self._send({"error": str(e)}, 400)
            except Exception as e:
                return self._send({"error": f"{action} 失败: {e}"}, 500)
            return self._send({"error": "未知 action"}, 400)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        action = body.get("action")
        if action == "toggle":
            set_cfg(enabled=not get_cfg()["enabled"])
        elif action == "reset_key":
            set_cfg(api_key=secrets.token_hex(24))
        elif action == "apply":
            ip = str(body.get("ip", "")).strip()
            try:
                port = int(body.get("port", 0))
            except (TypeError, ValueError):
                port = 0
            if ip and ip not in all_ips():
                return self._send({"error": f"IP 不在可选列表: {ip}"}, 400)
            if not (1024 <= port <= 65535):
                return self._send({"error": "端口需在 1024-65535"}, 400)
            old_port = int(get_cfg()["port"])
            if port == ADMIN_PORT:
                return self._send(
                    {"error": f"端口 {port} 是管理面端口，不可占用"}, 400)
            if port != old_port and not _port_free(port):
                return self._send({"error": f"端口 {port} 已被占用"}, 400)
            set_cfg(ip=ip or get_cfg()["ip"], port=port)
            if port != old_port:
                _schedule_restart()
            return self._send({**self._payload(), "restarting": port != old_port})
        elif "enabled" in body:
            set_cfg(enabled=bool(body["enabled"]))
        self._send(self._payload())

    def log_message(self, *a):  # 静默
        pass


def run_admin() -> None:
    ThreadingHTTPServer(("0.0.0.0", ADMIN_PORT), AdminHandler).serve_forever()


if __name__ == "__main__":
    threading.Thread(target=run_admin, daemon=True).start()
    cfg = get_cfg()
    uvicorn.run(app, host="0.0.0.0", port=int(cfg.get("port") or DEFAULT_PORT))
