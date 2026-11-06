#!/usr/bin/env bash
# ARL-AI 叠加安装：在【已有的原版灯塔】上直接叠加 MCP（数据零拷贝、零迁移）。
#
# 原理：
#   - compose 增量走 docker-compose.override.yml（compose 原生合并），原 docker-compose.yml 不动；
#     回滚 = 删 override 文件 + docker compose up -d web
#   - 前端注入目录独立（frontend-mcp），不覆盖镜像内文件
#   - MCP 服务跑在宿主机 systemd，只连灯塔 API，不碰数据库
#
# 依赖：docker + docker compose v2 + python3(venv/pip)；root 执行。
# 用法（同目录备好 arl_mcp/ mcp_service.py mcp_panel.js）：
#   bash overlay_install.sh --dir /opt/docker_arl --web-port 5003 \
#        --web-container arl_web --mcp-port 8010 --admin-port 8011 \
#        --arl-pass <原灯塔密码> --public-ip <公网IP可选>
set -euo pipefail

WEB_PORT=5003; WEB_CONTAINER=arl_web; MCP_PORT=8010; ADMIN_PORT=8011
ARL_PASS=arlpass; PUBLIC_IP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) ARL_DIR=$2; shift 2;;
    --web-port) WEB_PORT=$2; shift 2;;
    --web-container) WEB_CONTAINER=$2; shift 2;;
    --mcp-port) MCP_PORT=$2; shift 2;;
    --admin-port) ADMIN_PORT=$2; shift 2;;
    --arl-pass) ARL_PASS=$2; shift 2;;
    --public-ip) PUBLIC_IP=$2; shift 2;;
    *) echo "未知参数: $1"; exit 1;;
  esac
done
ARL_DIR=${ARL_DIR:-/opt/docker_arl}
MCP_DIR="$ARL_DIR/mcp"
SERVICE_NAME=mcp-ai
FILE_DIR="$(cd "$(dirname "$0")" && pwd)"   # mcp_service.py / mcp_panel.js 所在
PKG_DIR="$FILE_DIR"                          # arl_mcp/ 所在（git 仓库布局在上一级）
if [[ ! -d "$PKG_DIR/arl_mcp" ]]; then
  up="$PKG_DIR"
  for _ in 1 2 3; do
    up="$(dirname "$up")"
    [[ -d "$up/arl_mcp" ]] && PKG_DIR="$up" && break
  done
fi

say()  { echo -e "\n\033[1;36m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m[警告] $*\033[0m"; }
die()  { echo -e "\033[1;31m[失败] $*\033[0m"; exit 1; }

say "前置检查"
[[ $EUID -eq 0 ]] || die "请用 root 执行"
command -v docker >/dev/null || die "未安装 docker"
docker compose version >/dev/null 2>&1 || die "未安装 docker compose v2"
command -v python3 >/dev/null || die "未安装 python3"
python3 -m venv --help >/dev/null 2>&1 || die "python3 缺 venv 模块"
docker ps --format '{{.Names}}' | grep -qx "$WEB_CONTAINER" \
  || die "web 容器 $WEB_CONTAINER 未运行（原灯塔必须在线）"
ss -lnt | grep -qE ":$MCP_PORT |:$ADMIN_PORT " && die "端口 $MCP_PORT/$ADMIN_PORT 已被占用"
[[ -f "$ARL_DIR/docker-compose.yml" ]] || die "未找到 $ARL_DIR/docker-compose.yml"
[[ -f "$PKG_DIR/arl_mcp/server.py" && -f "$FILE_DIR/mcp_service.py" && -f "$FILE_DIR/mcp_panel.js" ]] \
  || die "缺少 arl_mcp/ 与 mcp_service.py、mcp_panel.js"
[[ -f "$ARL_DIR/docker-compose.override.yml" ]] \
  && die "已存在 override（可能装过），先删除再装: rm $ARL_DIR/docker-compose.override.yml"
curl -sk "https://127.0.0.1:$WEB_PORT/" | grep -q mcp_panel.js \
  && die "检测到前端已注入，勿重复安装"

# ---------- 备份 ----------
say "备份原状态（回滚依据）"
cp -a "$ARL_DIR/docker-compose.yml" "$ARL_DIR/docker-compose.yml.bak-mcp"
docker exec "$WEB_CONTAINER" cp /etc/nginx/nginx.conf /tmp/nginx.conf.orig 2>/dev/null \
  || warn "nginx.conf 容器内备份失败（继续，容器内文件本来就会被挂载覆盖）"

# ---------- 前端注入（独立目录） ----------
say "从 $WEB_CONTAINER 提取前端并注入 MCP 栏目"
rm -rf "$ARL_DIR/frontend-mcp"
docker cp "$WEB_CONTAINER:/code/frontend" "$ARL_DIR/frontend-mcp"
cp -a "$FILE_DIR/mcp_panel.js" "$ARL_DIR/frontend-mcp/mcp_panel.js"
python3 - "$ARL_DIR/frontend-mcp/index.html" <<'PYEOF'
import sys, io
p = sys.argv[1]
html = io.open(p, encoding="utf-8").read()
if 'mcp_panel.js' not in html:
    tag = '<script src=/mcp_panel.js?v=1></script>'
    low = html.lower()
    i = low.rindex('</body>')
    io.open(p, "w", encoding="utf-8").write(html[:i] + tag + html[i:])
    print("index.html 已注入")
else:
    print("index.html 已含注入")
PYEOF

# ---------- nginx 注入（独立文件） ----------
say "生成注入版 nginx.conf"
docker exec "$WEB_CONTAINER" cat /etc/nginx/nginx.conf > "$ARL_DIR/nginx-mcp.conf"
python3 - "$ARL_DIR/nginx-mcp.conf" "$ADMIN_PORT" <<'PYEOF'
import sys, io
p, admin_port = sys.argv[1], sys.argv[2]
conf = io.open(p, encoding="utf-8").read()
BLOCK = """
        location /mcp_admin/ {
            proxy_pass http://host.docker.internal:%s/admin/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 5s;
            proxy_read_timeout 30s;
        }
""" % admin_port
if "/mcp_admin/" not in conf:
    i = conf.index("        error_page 497")          # 443 server
    conf = conf[:i] + BLOCK + "\n" + conf[i:]
    j = conf.index("        location /swaggerui/")    # 80 server
    conf = conf[:j] + BLOCK + "\n" + conf[j:]
    io.open(p, "w", encoding="utf-8").write(conf)
    print("nginx.conf 已注入 80/443")
else:
    print("nginx.conf 已含注入")
PYEOF

# ---------- compose 增量（override，原 compose 不动） ----------
say "写入 docker-compose.override.yml（原 compose 零改动）"
cat > "$ARL_DIR/docker-compose.override.yml" <<EOF
services:
  web:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./frontend-mcp:/code/frontend
      - ./nginx-mcp.conf:/etc/nginx/nginx.conf:ro
EOF
docker compose -f "$ARL_DIR/docker-compose.yml" \
               -f "$ARL_DIR/docker-compose.override.yml" config >/dev/null \
  || { warn "override 校验失败，回滚"; rm "$ARL_DIR/docker-compose.override.yml"; die "compose 合并校验不通过"; }

# ---------- 重建 web 容器（worker/scheduler/数据不动） ----------
say "重建 web 容器（约 30 秒界面中断；正在跑的扫描任务不受影响）"
cd "$ARL_DIR"
docker compose up -d web
ok=""
for i in $(seq 1 30); do
  [[ "$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$WEB_PORT/" || true)" == "200" ]] && ok=1 && break
  sleep 2
done
[[ -n "$ok" ]] || die "web 重建后未就绪（docker compose logs web 排查）"
curl -sk "https://127.0.0.1:$WEB_PORT/" | grep -q mcp_panel.js || die "前端注入未生效"
echo "web 已恢复，注入生效"

# ---------- MCP 服务 ----------
say "安装 MCP 服务"
mkdir -p "$MCP_DIR/arl_mcp"
cp -a "$PKG_DIR"/arl_mcp/*.py "$MCP_DIR/arl_mcp/"
cp -a "$FILE_DIR/mcp_service.py" "$MCP_DIR/mcp_service.py"
python3 -m venv "$MCP_DIR/.venv"
"$MCP_DIR/.venv/bin/pip" install -q --upgrade pip \
  -i "${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
"$MCP_DIR/.venv/bin/pip" install -q "mcp>=1.2,<2" httpx uvicorn \
  -i "${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if command -v systemctl >/dev/null; then
  cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=ARL MCP Service (overlay on existing ARL)
After=network.target docker.service

[Service]
WorkingDirectory=$MCP_DIR
Environment=PYTHONPATH=$MCP_DIR
Environment=ARL_URL=https://127.0.0.1:$WEB_PORT
Environment=ARL_MCP_WORKSPACE=$MCP_DIR
Environment=ARL_USER=admin
Environment=ARL_PASS=$ARL_PASS
Environment=MCP_PORT=$MCP_PORT
Environment=MCP_ADMIN_PORT=$ADMIN_PORT
${PUBLIC_IP:+Environment=MCP_PUBLIC_IP=$PUBLIC_IP
}ExecStart=$MCP_DIR/.venv/bin/python $MCP_DIR/mcp_service.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
else
  warn "无 systemd，手动启动: ARL_URL=https://127.0.0.1:$WEB_PORT ARL_MCP_WORKSPACE=$MCP_DIR MCP_PORT=$MCP_PORT MCP_ADMIN_PORT=$ADMIN_PORT $MCP_DIR/.venv/bin/python $MCP_DIR/mcp_service.py"
fi

# ---------- 验证 ----------
say "验证"
ok=""
for i in $(seq 1 15); do
  curl -s "http://127.0.0.1:$ADMIN_PORT/admin/config" | grep -q api_key && ok=1 && break
  sleep 2
done
[[ -n "$ok" ]] || die "MCP 管理面未就绪（journalctl -u $SERVICE_NAME）"
curl -sk "https://127.0.0.1:$WEB_PORT/mcp_admin/config" | head -c 120; echo " <- 面板 API"
curl -s -o /dev/null -w "数据面无密钥 %{http_code}（应为 401）\n" -X POST \
  "http://127.0.0.1:$MCP_PORT/mcp" -H 'Content-Type: application/json' -d '{}' || true

IP_SHOW="${PUBLIC_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
cat <<EOF

==============================================================
 叠加安装完成（原灯塔数据全量可用，无需任何拷贝）
  灯塔 UI         : https://$IP_SHOW:$WEB_PORT  （登录后左侧菜单「MCP服务器」）
  MCP 服务        : http://$IP_SHOW:$MCP_PORT/mcp  （默认关闭，UI 里开）
  服务管理        : systemctl {status|restart|stop} $SERVICE_NAME
  密钥            : UI 面板里复制（X-API-Key 请求头鉴权）
  MCP 服务目录    : $MCP_DIR
  【回滚】完全卸载 :
    systemctl disable --now $SERVICE_NAME && rm -f /etc/systemd/system/$SERVICE_NAME.service
    rm -rf $ARL_DIR/docker-compose.override.yml $ARL_DIR/frontend-mcp \
           $ARL_DIR/nginx-mcp.conf $ARL_DIR/mcp $ARL_DIR/docker-compose.yml.bak-mcp
    cd $ARL_DIR && docker compose up -d web
  （回滚后灯塔回到原版状态，数据不受任何影响）
==============================================================
EOF
