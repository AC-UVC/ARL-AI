#!/usr/bin/env bash
# ARL-AI 叠加安装：在【已有的原版灯塔】上直接叠加 MCP（数据零拷贝、零迁移）。
#
# 原理：
#   - compose 增量走 docker-compose.override.yml（compose 原生合并），原 docker-compose.yml 不动；
#     回滚 = 删 override 文件 + docker compose up -d web
#   - 前端注入目录独立（frontend-mcp），不覆盖镜像内文件
#   - MCP 服务跑在宿主机 systemd，只连灯塔 API；
#   - 会在灯塔 Mongo 里【新增】一个 arl_mcp 专用账号（不动 admin 及任何业务数据）：
#     ARL 每用户只存一个 token、登录即覆盖旧 token，若 MCP 与人共用 admin 账号，
#     AI 每次调用都会把浏览器的登录态顶下线。专用账号只覆盖自己的 token。
#     （账号口令仅存于 systemd unit 的 Environment，安装结束打印一次）
#
# 依赖：docker + docker compose v2 + python3(venv/pip)；root 执行。
# 用法（同目录备好 arl_mcp/ mcp_service.py mcp_panel.js）：
#   bash overlay_install.sh --dir /opt/docker_arl --web-port 5003 \
#        --web-container arl_web --mcp-port 8010 --admin-port 8011 \
#        --public-ip <公网IP可选>
#   （--arl-pass 已废弃：MCP 不再用 admin 凭据，保留参数仅为兼容旧命令行）
set -euo pipefail

WEB_PORT=5003; WEB_CONTAINER=arl_web; MCP_PORT=8010; ADMIN_PORT=8011
PUBLIC_IP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) ARL_DIR=$2; shift 2;;
    --web-port) WEB_PORT=$2; shift 2;;
    --web-container) WEB_CONTAINER=$2; shift 2;;
    --mcp-port) MCP_PORT=$2; shift 2;;
    --admin-port) ADMIN_PORT=$2; shift 2;;
    --arl-pass) warn "--arl-pass 已废弃（MCP 改用专用账号 arl_mcp），参数忽略"; shift 2;;
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
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  say "缺 python3-venv，自动安装（Ubuntu 需要它 venv 里才有 pip）"
  if command -v apt-get >/dev/null; then
    apt-get update -qq >/dev/null 2>&1
    apt-get install -y -qq python3-venv python3-pip >/dev/null 2>&1 \
      || die "python3-venv 自动安装失败，请手动执行: apt-get install -y python3-venv python3-pip"
  elif command -v dnf >/dev/null; then
    dnf install -y -q python3-pip >/dev/null 2>&1 || die "python3-pip 自动安装失败"
  elif command -v yum >/dev/null; then
    yum install -y -q python3-pip >/dev/null 2>&1 || die "python3-pip 自动安装失败"
  else
    die "系统缺少 python venv/pip 支持，请手动安装后重试"
  fi
fi
docker ps --format '{{.Names}}' | grep -qx "$WEB_CONTAINER" \
  || die "web 容器 $WEB_CONTAINER 未运行（原灯塔必须在线）"
ss -lnt | grep -qE ":$MCP_PORT |:$ADMIN_PORT " && die "端口 $MCP_PORT/$ADMIN_PORT 已被占用"
[[ -f "$ARL_DIR/docker-compose.yml" ]] || die "未找到 $ARL_DIR/docker-compose.yml"
[[ -f "$PKG_DIR/arl_mcp/server.py" && -f "$FILE_DIR/mcp_service.py" && -f "$FILE_DIR/mcp_panel.js" ]] \
  || die "缺少 arl_mcp/ 与 mcp_service.py、mcp_panel.js"
if [[ -f "$ARL_DIR/docker-compose.override.yml" ]]; then
  grep -q frontend-mcp "$ARL_DIR/docker-compose.override.yml" \
    && warn "检测到上次安装残留（可能中途失败），继续覆盖安装（幂等）" \
    || die "已存在第三方 docker-compose.override.yml，为避免冲突请人工确认后移除"
fi
curl -sk "https://127.0.0.1:$WEB_PORT/" | grep -q mcp_panel.js \
  && warn "前端已注入过 MCP，继续覆盖（幂等）"

# ---------- 备份 ----------
say "备份原状态（回滚依据）"
cp -a "$ARL_DIR/docker-compose.yml" "$ARL_DIR/docker-compose.yml.bak-mcp"
docker exec "$WEB_CONTAINER" cp /etc/nginx/nginx.conf /tmp/nginx.conf.orig 2>/dev/null \
  || warn "nginx.conf 容器内备份失败（继续，容器内文件本来就会被挂载覆盖）"

# ---------- 前端注入（独立目录） ----------
# 从镜像提取出厂原始前端/nginx（重装时容器内 /code/frontend 已被挂载覆盖，不可用）
say "从镜像提取原始前端并注入 MCP 栏目"
WEB_IMAGE=$(docker inspect "$WEB_CONTAINER" --format '{{.Config.Image}}')
TMP_C=$(docker create "$WEB_IMAGE") || die "无法从镜像 $WEB_IMAGE 创建临时容器"
rm -rf "$ARL_DIR/frontend-mcp"
docker cp "$TMP_C:/code/frontend" "$ARL_DIR/frontend-mcp" || { docker rm -f "$TMP_C" >/dev/null 2>&1; die "前端提取失败（镜像内未找到 /code/frontend）"; }
docker cp "$TMP_C:/etc/nginx/nginx.conf" "$ARL_DIR/nginx-mcp.conf" || { docker rm -f "$TMP_C" >/dev/null 2>&1; die "nginx.conf 提取失败"; }
docker rm "$TMP_C" >/dev/null
[[ -f "$ARL_DIR/frontend-mcp/index.html" ]] || die "前端提取不完整（index.html 缺失）"
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
# --force-recreate：重装时配置未变 compose 不会重建容器，但宿主目录已被
# rm -rf 重建，旧容器还绑着已删除的目录 inode（容器内目录为空 → 403）
docker compose up -d --force-recreate web
ok=""
for i in $(seq 1 30); do
  [[ "$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$WEB_PORT/" || true)" == "200" ]] && ok=1 && break
  sleep 2
done
[[ -n "$ok" ]] || die "web 重建后未就绪（docker compose logs web 排查）"
curl -sk "https://127.0.0.1:$WEB_PORT/" | grep -q mcp_panel.js || die "前端注入未生效"
echo "web 已恢复，注入生效"

# ---------- MCP 专用账号（防挤占 admin 登录态） ----------
say "创建 MCP 专用账号 arl_mcp（ARL 登录会覆盖同账号旧 token，专用账号互不影响）"
MONGO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -i mongo | head -1)
[[ -n "$MONGO_CONTAINER" ]] || die "未找到 mongo 容器"
MONGO_CLIENT=$(docker exec "$MONGO_CONTAINER" sh -c 'command -v mongosh || command -v mongo')
[[ -n "$MONGO_CLIENT" ]] || die "mongo 容器内无 mongo/mongosh 客户端"
read -r MONGO_USER MONGO_PASS MONGO_DB <<< "$(docker exec "$WEB_CONTAINER" python3 -c "
import re
s = open('/code/app/config.yaml').read()
m = re.search(r\"URI\s*:\s*'mongodb://([^:]+):([^@]+)@\", s)
d = re.search(r\"DB\s*:\s*'([^']+)'\", s)
print(m.group(1), m.group(2), d.group(1))
")"
[[ -n "$MONGO_DB" ]] || die "无法从 web 容器读取 MONGO 配置"
MCP_USER_NAME=arl_mcp
MCP_USER_PASS=$(python3 -c "import secrets;print(secrets.token_urlsafe(18))")
HASH=$(python3 -c "import hashlib;print(hashlib.md5(('arlsalt!@#'+'$MCP_USER_PASS').encode()).hexdigest())")
docker exec "$MONGO_CONTAINER" "$MONGO_CLIENT" -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
var c = db.getSiblingDB('$MONGO_DB').user;
var doc = c.findOne({username: '$MCP_USER_NAME'});
if (doc) { c.updateOne({username: '$MCP_USER_NAME'}, {\$set: {password: '$HASH'}}); }
else { c.insertOne({username: '$MCP_USER_NAME', password: '$HASH', token: null}); }
print('arl_mcp ready')
" | grep -q "arl_mcp ready" || die "创建 arl_mcp 账号失败"
curl -sk -X POST "https://127.0.0.1:$WEB_PORT/api/user/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$MCP_USER_NAME\",\"password\":\"$MCP_USER_PASS\"}" \
  | grep -q '"code":200' || die "arl_mcp 登录验证失败（灯塔 API 不通或账号异常）"
echo "arl_mcp 账号就绪，登录验证通过"

# ---------- MCP 服务 ----------
say "安装 MCP 服务"
mkdir -p "$MCP_DIR/arl_mcp"
cp -a "$PKG_DIR"/arl_mcp/*.py "$MCP_DIR/arl_mcp/"
cp -a "$FILE_DIR/mcp_service.py" "$MCP_DIR/mcp_service.py"
python3 -m venv --clear "$MCP_DIR/.venv"
[[ -x "$MCP_DIR/.venv/bin/pip" ]] || die "venv 内无 pip（python3-venv 未装好），请手动: apt-get install -y python3-venv"
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
Environment=ARL_USER=$MCP_USER_NAME
Environment=ARL_PASS=$MCP_USER_PASS
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
  MCP 专用账号    : $MCP_USER_NAME / $MCP_USER_PASS（勿用此账号登录浏览器；重装会重置口令）
  MCP 服务目录    : $MCP_DIR
  【回滚】完全卸载 :
    systemctl disable --now $SERVICE_NAME && rm -f /etc/systemd/system/$SERVICE_NAME.service
    rm -rf $ARL_DIR/docker-compose.override.yml $ARL_DIR/frontend-mcp \
           $ARL_DIR/nginx-mcp.conf $ARL_DIR/mcp $ARL_DIR/docker-compose.yml.bak-mcp
    cd $ARL_DIR && docker compose up -d web
  （回滚后灯塔回到原版状态，数据不受任何影响）
==============================================================
EOF
