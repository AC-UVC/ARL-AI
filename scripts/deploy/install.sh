#!/usr/bin/env bash
# ARL-AI 一键部署脚本：原版灯塔(compose) + MCP 服务(systemd) 一次装完。
# 依赖：docker + docker compose v2 + python3(venv/pip)；root 执行。
#
# 用法（在同目录准备 arl_mcp/ mcp_service.py mcp_panel.js）：
#   bash install.sh
#   bash install.sh --web-port 5003 --http-port 5005 --mcp-port 8010 \
#                   --admin-port 8011 --prefix arl --dir /opt/docker_arl_ai \
#                   --public-ip 1.2.3.4 --image swr.cn-south-1.myhuaweicloud.com/mingy/arl:latest
set -euo pipefail

# ---------- 参数 ----------
WEB_PORT=5003; HTTP_PORT=5005; MCP_PORT=8010; ADMIN_PORT=8011
PREFIX=arl; INSTALL_DIR=/opt/docker_arl_ai; SERVICE_NAME=mcp-ai
PUBLIC_IP=""; IMAGE="swr.cn-south-1.myhuaweicloud.com/mingy/arl:latest"
PIP_INDEX="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --web-port) WEB_PORT=$2; shift 2;;
    --http-port) HTTP_PORT=$2; shift 2;;
    --mcp-port) MCP_PORT=$2; shift 2;;
    --admin-port) ADMIN_PORT=$2; shift 2;;
    --prefix) PREFIX=$2; shift 2;;
    --dir) INSTALL_DIR=$2; shift 2;;
    --service) SERVICE_NAME=$2; shift 2;;
    --public-ip) PUBLIC_IP=$2; shift 2;;
    --image) IMAGE=$2; shift 2;;
    *) echo "未知参数: $1"; exit 1;;
  esac
done
ASSETS="$(cd "$(dirname "$0")" && pwd)"
# arl_mcp/ 可能与脚本同目录，也可能在工程根（仓库布局）——自动向上查找
if [[ ! -d "$ASSETS/arl_mcp" ]]; then
  up="$ASSETS"
  for _ in 1 2 3; do
    up="$(dirname "$up")"
    [[ -d "$up/arl_mcp" ]] && ASSETS="$up" && break
  done
fi

say()  { echo -e "\n\033[1;36m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m[警告] $*\033[0m"; }
die()  { echo -e "\033[1;31m[失败] $*\033[0m"; exit 1; }

# ---------- 前置检查 ----------
say "前置检查"
[[ $EUID -eq 0 ]] || die "请用 root 执行"
command -v docker >/dev/null || die "未安装 docker"
docker compose version >/dev/null 2>&1 || die "未安装 docker compose v2"
command -v python3 >/dev/null || die "未安装 python3"
python3 -m venv --help >/dev/null 2>&1 || die "python3 缺 venv 模块（安装 python3-venv）"
for p in "$WEB_PORT" "$HTTP_PORT" "$MCP_PORT" "$ADMIN_PORT"; do
  ss -lnt | grep -q ":$p " && die "端口 $p 已被占用"
done
[[ -f "$ASSETS/arl_mcp/server.py" && -f "$ASSETS/mcp_service.py" ]] \
  || die "缺少 arl_mcp/ 与 mcp_service.py（应与 install.sh 同目录或在工程根）"
[[ -f "$ASSETS/mcp_panel.js" ]] || die "缺少 mcp_panel.js"
[[ -d "$INSTALL_DIR" ]] && die "部署目录已存在: $INSTALL_DIR"
docker image inspect "$IMAGE" >/dev/null 2>&1 || warn "镜像 $IMAGE 本地不存在，将尝试拉取"

# ---------- 灯塔 compose ----------
say "写入灯塔部署文件 ($INSTALL_DIR)"
mkdir -p "$INSTALL_DIR"
cat > "$INSTALL_DIR/docker-compose.yml" <<EOF
volumes:
  arl_db:

services:
    web:
        image: $IMAGE
        container_name: ${PREFIX}_web
        restart: unless-stopped
        depends_on: [mongodb, rabbitmq]
        ports:
          - "$WEB_PORT:443"
          - "$HTTP_PORT:80"
        extra_hosts:
          - "host.docker.internal:host-gateway"
        volumes:
          - ./arl_web.log:/code/arl_web.log
          - ./config-docker.yaml:/code/app/config.yaml
          - ./image:/code/app/tmp_screenshot
          - ./poc:/opt/ARL-NPoC/xing/plugins/upload_poc
          - ./frontend:/code/frontend
          - ./nginx.conf:/etc/nginx/nginx.conf:ro
        entrypoint: ["sh", "-c", "gen_crt.sh; nginx; wait-for-it.sh mongodb:27017; wait-for-it.sh rabbitmq:5672; gunicorn -b 0.0.0.0:5003 app.main:arl_app -w 3 --access-logfile arl_web.log --access-logformat '%({x-real-ip}i)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\"'"]
        environment:
          - LANG=en_US.UTF-8
          - TZ=Asia/Shanghai

    worker:
        image: $IMAGE
        container_name: ${PREFIX}_worker
        restart: unless-stopped
        depends_on: [mongodb, rabbitmq]
        volumes:
          - ./arl_worker.log:/code/arl_worker.log
          - ./config-docker.yaml:/code/app/config.yaml
          - ./image:/code/app/tmp_screenshot
          - ./poc:/opt/ARL-NPoC/xing/plugins/upload_poc
        entrypoint: ["sh", "-c", "wait-for-it.sh mongodb:27017; wait-for-it.sh rabbitmq:5672; celery -A app.celerytask.celery worker -l info -Q arlgithub -n arlgithub -c 2 -O fair -f arl_worker.log & celery -A app.celerytask.celery worker -l info -Q arltask -n arltask -c 2 -O fair -f arl_worker.log"]
        environment:
          - LANG=en_US.UTF-8
          - TZ=Asia/Shanghai

    scheduler:
      image: $IMAGE
      container_name: ${PREFIX}_scheduler
      restart: unless-stopped
      depends_on: [mongodb, rabbitmq]
      volumes:
        - ./config-docker.yaml:/code/app/config.yaml
      entrypoint: [ "sh", "-c", "wait-for-it.sh mongodb:27017; wait-for-it.sh rabbitmq:5672; python3.6 -m app.scheduler" ]
      environment:
        - LANG=en_US.UTF-8
        - TZ=Asia/Shanghai

    mongodb:
        image: swr.cn-south-1.myhuaweicloud.com/mingy/mongo:4.0.27
        container_name: ${PREFIX}_mongodb
        restart: always
        ports:
          - "127.0.0.1:$((ADMIN_PORT+1)):27017"
        volumes:
          - arl_db:/data/db
          - ./mongo-init.js:/docker-entrypoint-initdb.d/mongo-init.js:ro
        environment:
          - MONGO_INITDB_DATABASE=arl
          - MONGO_INITDB_ROOT_USERNAME=admin
          - MONGO_INITDB_ROOT_PASSWORD=admin

    rabbitmq:
      image: swr.cn-south-1.myhuaweicloud.com/mingy/rabbitmq:3.8.19-management-alpine
      container_name: ${PREFIX}_rabbitmq
      restart: always
      environment:
        - RABBITMQ_DEFAULT_PASS=arlpassword
        - RABBITMQ_DEFAULT_USER=arl
        - RABBITMQ_DEFAULT_VHOST=arlv2host
      logging:
        driver: "json-file"
        options: {max-size: "1M", max-file: "10"}
EOF

cat > "$INSTALL_DIR/mongo-init.js" <<'EOF'
db.user.drop()
db.user.insert({ username: 'admin',  password: hex_md5('arlsalt!@#'+'arlpass') })
EOF

cat > "$INSTALL_DIR/config-docker.yaml" <<'EOF'
CELERY:
  BROKER_URL : "amqp://arl:arlpassword@rabbitmq:5672/arlv2host"

MONGO:
  URI : 'mongodb://admin:admin@mongodb:27017/'
  DB : 'arl'

GEOIP:
  CITY: '/data/GeoLite2/GeoLite2-City.mmdb'
  ASN: '/data/GeoLite2/GeoLite2-ASN.mmdb'

FOFA:
  URL: "https://fofoapi.com/"
  EMAIL: ""
  KEY: ""

QUERY_PLUGIN:
  alienvault: {enable: true}
  certspotter: {after_id: 1, max_page: 3, enable: true}
  crtsh: {enable: true}
  fofa: {enable: false}
  hunter_qax: {api_key: "", page_size: 100, max_page: 5, enable: false}
  passivetotal: {auth_email: "", auth_key: "", enable: false}
  quake_360: {api_key: "", max_size: 500, enable: false}
  rapiddns: {enable: true}
  securitytrails: {api_key: "", enable: false}
  virustotal: {api_key: "", enable: false}
  zoomeye: {api_key: "", max_page: 20, enable: false}
  chaos: {api_key: "", enable: false}

DINGDING: {SECRET: "", ACCESS_TOKEN: ""}
EMAIL: {HOST: "", PORT: "", USERNAME: "", PASSWORD: "", TO: ""}
FEISHU: {WEBHOOK_URL: "", SECRET: ""}
WXWORK: {WEBHOOK_URL: ""}
WEBHOOK: {URL: "", TOKEN: ""}
GITHUB: {TOKEN: ""}
PROXY: {HTTP_URL: ""}

ARL:
  AUTH: true
  API_KEY: ""
  BLACK_IPS:
    - 127.0.0.0/8
    - 0.0.0.0/8
    - 172.16.0.0/12
    - 100.64.0.0/10
  FORBIDDEN_DOMAINS:
    - gov.cn
  PORT_TOP_10: "80,443,8443,8080,8081,8888,8089,5000,5001,8085,800,81,9000,88,8001,8090"
  DOMAIN_DICT: "/code/app/dicts/domain_2w.txt"
  FILE_LEAK_DICT: "/code/app/dicts/file_top_2000.txt"
  DOMAIN_BRUTE_CONCURRENT: 300
  ALT_DNS_CONCURRENT: 1500
EOF

touch "$INSTALL_DIR/arl_web.log" "$INSTALL_DIR/arl_worker.log"
cp -a "$ASSETS/mcp_panel.js" "$INSTALL_DIR/mcp_panel.js"

# ---------- 前端与 nginx（从镜像拷出并注入） ----------
say "从镜像提取前端并注入 MCP 栏目"
docker create --name "${PREFIX}_tmp" "$IMAGE" >/dev/null
docker cp "${PREFIX}_tmp:/code/frontend" "$INSTALL_DIR/frontend"
docker cp "${PREFIX}_tmp:/etc/nginx/nginx.conf" "$INSTALL_DIR/nginx.conf"
docker rm -f "${PREFIX}_tmp" >/dev/null

python3 - "$INSTALL_DIR" "$ADMIN_PORT" <<'PYEOF'
import sys, io
d, admin_port = sys.argv[1], sys.argv[2]

p = d + "/frontend/index.html"
html = io.open(p, encoding="utf-8").read()
tag = '<script src=/mcp_panel.js?v=1></script>'
if 'mcp_panel.js' not in html:
    low = html.lower()
    i = low.rindex('</body>')
    html = html[:i] + tag + html[i:]
    io.open(p, "w", encoding="utf-8").write(html)
print("index.html 已注入")

BLOCK = """
        location /mcp_admin/ {
            proxy_pass http://host.docker.internal:%s/admin/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 5s;
            proxy_read_timeout 30s;
        }
""" % admin_port

p = d + "/nginx.conf"
conf = io.open(p, encoding="utf-8").read()
if "/mcp_admin/" not in conf:
    marker = "        error_page 497"
    i = conf.index(marker)
    conf = conf[:i] + BLOCK + "\n" + conf[i:]
    marker2 = "        location /swaggerui/"
    j = conf.index(marker2)
    conf = conf[:j] + BLOCK + "\n" + conf[j:]
    io.open(p, "w", encoding="utf-8").write(conf)
print("nginx.conf 已注入 80/443 两个 server")
PYEOF

# ---------- 启动灯塔 ----------
say "启动灯塔容器组"
cd "$INSTALL_DIR"
docker compose up -d

# ---------- MCP 服务 ----------
say "安装 MCP 服务 (venv + 依赖)"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip -i "$PIP_INDEX"
"$INSTALL_DIR/.venv/bin/pip" install -q "mcp>=1.2,<2" httpx uvicorn -i "$PIP_INDEX"
mkdir -p "$INSTALL_DIR/arl_mcp"
cp -a "$ASSETS"/arl_mcp/*.py "$INSTALL_DIR/arl_mcp/"
cp -a "$ASSETS/mcp_service.py" "$INSTALL_DIR/mcp_service.py"

if command -v systemctl >/dev/null; then
  say "写入 systemd 服务 ($SERVICE_NAME)"
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=ARL MCP Service (FastMCP streamable-http)
After=network.target docker.service

[Service]
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
Environment=ARL_URL=https://127.0.0.1:$WEB_PORT
Environment=ARL_MCP_WORKSPACE=$INSTALL_DIR
Environment=ARL_USER=admin
Environment=ARL_PASS=arlpass
Environment=MCP_PORT=$MCP_PORT
Environment=MCP_ADMIN_PORT=$ADMIN_PORT
${PUBLIC_IP:+Environment=MCP_PUBLIC_IP=$PUBLIC_IP
}ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/mcp_service.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
else
  warn "无 systemd，请手动启动: ARL_URL=https://127.0.0.1:$WEB_PORT ARL_MCP_WORKSPACE=$INSTALL_DIR MCP_PORT=$MCP_PORT MCP_ADMIN_PORT=$ADMIN_PORT $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/mcp_service.py"
fi

# ---------- 就绪等待与验证 ----------
say "等待服务就绪"
ok=""
for i in $(seq 1 30); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$WEB_PORT/" || true)
  [[ "$code" == "200" ]] && ok=web && break
  sleep 2
done
[[ -n "$ok" ]] || die "灯塔 Web 未就绪（docker compose logs 查看日志）"
for i in $(seq 1 15); do
  curl -s "http://127.0.0.1:$ADMIN_PORT/admin/config" | grep -q api_key && ok=mcp && break
  sleep 2
done
[[ "$ok" == "mcp" ]] || die "MCP 管理面未就绪（journalctl -u $SERVICE_NAME 查看日志）"
curl -s -o /dev/null -w "HTTP 入口 %{http_code}\n" "http://127.0.0.1:$HTTP_PORT/"
curl -s "http://127.0.0.1:$HTTP_PORT/mcp_admin/config" | head -c 120; echo " <- 面板 API"
curl -s -o /dev/null -w "数据面无密钥 %{http_code}（应为 401）\n" -X POST \
  "http://127.0.0.1:$MCP_PORT/mcp" -H 'Content-Type: application/json' -d '{}' || true

IP_SHOW="${PUBLIC_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
cat <<EOF

==============================================================
 部署完成
  灯塔 UI        : https://$(hostname -s):$WEB_PORT  (http://$IP_SHOW:$HTTP_PORT)
  默认账号       : admin / arlpass
  MCP 服务       : http://$IP_SHOW:$MCP_PORT/mcp   (默认关闭，UI 里开)
  服务管理       : systemctl {status|restart|stop} $SERVICE_NAME
  UI 入口        : 登录灯塔 -> 左侧菜单最底部「MCP服务器」
  密钥           : 在 UI 面板复制（X-API-Key 请求头鉴权）
  数据目录       : $INSTALL_DIR
  完全卸载       : cd $INSTALL_DIR && docker compose down -v &&
                   systemctl disable --now $SERVICE_NAME &&
                   rm -rf $INSTALL_DIR /etc/systemd/system/$SERVICE_NAME.service
==============================================================
EOF
