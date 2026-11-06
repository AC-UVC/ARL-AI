# ARL-AI：ARL 资产侦察灯塔 + AI MCP

在 [yijingsec/ARL](https://gitee.com/yijingsec/ARL)（灯塔）之上加了 **MCP 服务**，
AI（ZCode / Claude 等）可直接增删改查灯塔的任务与资产；灯塔 UI 左侧菜单带 **MCP 栏目**
（开关 / 密钥 / 监听 IP 与端口全部在界面上管理）。

## 目录结构

```
arl_mcp/                     MCP 核心包
├── server.py                   25 个 MCP 工具定义
├── arl_client.py               ARL REST API 客户端（对齐 app/routes 源码）
├── fs_sandbox.py               文件沙箱：增删改查/临时文件只许在工作目录内
├── url_guard.py                SSRF 防护
└── config.py                   环境变量配置
scripts/deploy/              部署与运维脚本
├── mcp_service.py              MCP 服务入口（数据面 + 管理面）
├── mcp_panel.js                灯塔前端注入脚本（MCP 菜单 + 管理面板）
├── docker-compose.arl-ai.yml   独立灯塔容器组模板
└── *.py                        Kali 测试用部署脚本
tests/                       pytest 测试（48 项）
scripts/test_mcp_http.py     MCP 客户端端到端回归
```

## 架构

```
灯塔 UI(5004/5005) ── /mcp_admin/ (nginx 同源代理) ──> 管理面 :8011
       │                                               （开关/密钥/IP/端口，来源限内网）
AI 客户端 ── X-API-Key 请求头 ──────────────────────> 数据面 :用户可选端口（默认 8010）
                                                      （FastMCP streamable-http）
```

- **数据面**：FastMCP streamable-http，监听 `0.0.0.0:<端口>`，强制请求头鉴权
  `X-API-Key`（兼容 `Authorization: Bearer`），URL 传参不支持。
- **管理面**：固定端口 8011（nginx 代理目标，改数据面端口不影响面板），来源白名单
  默认 `127./10./172./192.168.` 前缀，可用 `MCP_ADMIN_ALLOW` 覆盖。
- 开关/密钥/IP/端口存 `<工作目录>/mcp_config.json`（原子写）。

## 灯塔 UI 的 MCP 栏目

左侧菜单底部「MCP」→ 管理面板：

| 功能 | 说明 |
|---|---|
| 服务状态 | 开/关服务，关闭后 AI 一律 403 |
| 监听设置 | 连接地址 IP 可选（枚举网卡 + `MCP_PUBLIC_IP`），端口可选，改端口自动重启生效（带占用预检，防止重启死循环） |
| 调用密钥 | 运行时生成 48 位 hex，可重置；缺失/错误一律 401 |
| 客户端配置 | 一键复制带 `X-API-Key` 请求头的 MCP 客户端 JSON |

## 部署到服务器

### 方式一：一键部署（推荐）

把工作目录拷到服务器，进入 `scripts/deploy/` 执行：

```bash
cd scripts/deploy
bash install.sh                                   # 默认端口 5003/5005/8010/8011
# 或自定义：
bash install.sh --web-port 5003 --http-port 5005 \
                --mcp-port 8010 --admin-port 8011 \
                --prefix arl --dir /opt/docker_arl_ai \
                --service mcp-ai --public-ip <服务器公网IP>
```

脚本自动完成：前置检查 → 写 compose/配置 → **从镜像提取前端并注入 MCP 栏目** →
注入 nginx 代理 → 启动容器组 → 安装 MCP 服务（venv + `mcp>=1.2,<2`）→ 写 systemd →
就绪等待 → 自检（Web/面板 API/数据面 401）→ 输出地址与卸载命令。
需要在 `scripts/deploy/` 同目录备好 `arl_mcp/`、`mcp_service.py`、`mcp_panel.js`（工程里都有）。
镜像默认 `swr.cn-south-1.myhuaweicloud.com/mingy/arl:latest`，可 `--image` 换源或提前 `docker load`。

### 方式二：手动分步部署

### 前置

- 已按 ARL 官方方式运行的灯塔（本方案用 `docker compose`，项目目录示例 `/opt/docker_arl_ai`，
  容器名/端口/卷与原灯塔完全隔离）
- Python ≥ 3.10（宿主机跑 MCP 服务，`pip install "mcp>=1.2,<2" httpx uvicorn`；
  **注意必须 <2**，mcp 2.x 已把 FastMCP 改名）
- 前端注入：从 `arl_web` 容器拷出 `/code/frontend`，将 `mcp_panel.js` 放入并在
  `index.html` 的 `</body>` 前加 `<script src=/mcp_panel.js?v=1></script>`，目录挂载回容器

### nginx（灯塔 web 容器）

443 与 80 两个 server 块都加：

```nginx
location /mcp_admin/ {
    proxy_pass http://host.docker.internal:8011/admin/;   # 需 extra_hosts: host-gateway
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

compose 里 web 服务加 `extra_hosts: ["host.docker.internal:host-gateway"]`。

### systemd（`/etc/systemd/system/mcp-ai.service`）

```ini
[Service]
WorkingDirectory=/opt/arl-ai
Environment=PYTHONPATH=/opt/arl-ai
Environment=ARL_URL=https://127.0.0.1:5004
Environment=ARL_MCP_WORKSPACE=/opt/arl-ai
Environment=ARL_USER=admin
Environment=ARL_PASS=<灯塔密码>
Environment=MCP_PORT=8010
Environment=MCP_ADMIN_PORT=8011
ExecStart=/opt/arl-ai/.venv/bin/python /opt/arl-ai/mcp_service.py
Restart=always
```

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `ARL_URL` | `http://127.0.0.1:5003` | 灯塔地址（https 自签可连） |
| `ARL_USER` / `ARL_PASS` | `admin` / `arlpass` | 灯塔登录账密 |
| `ARL_TOKEN` | 空 | 固定 Token（可配 `ARL.API_KEY`）；留空则账密自动登录 |
| `ARL_MCP_WORKSPACE` | 启动目录 | **文件沙箱根，必须设置**，AI 的文件读写/临时文件只允许在此 |
| `MCP_PORT` | `8010` | 数据面默认端口（UI 可改，存状态文件） |
| `MCP_ADMIN_PORT` | `8011` | 管理面固定端口 |
| `MCP_PUBLIC_IP` | 空 | 公网 IP，加入 UI 的 IP 下拉 |
| `MCP_ADMIN_ALLOW` | `127.,10.,172.,192.168.` | 管理面来源白名单前缀（逗号分隔） |
| `ARL_MCP_STRICT_URL_GUARD` | `0` | 设 `1` 后对 ARL 地址也做完整 SSRF 校验 |
| `ARL_TIMEOUT` / `ARL_TLS_VERIFY` | `30` / `0` | 超时秒 / 自签证书校验 |

### 部署检查单

1. `systemctl status <SERVICE_NAME>` 为 active（一键部署脚本末尾会自动做完 1–6）
2. `curl http://127.0.0.1:<ADMIN_PORT>/admin/config` 返回 JSON（密钥非空）
3. 经灯塔地址 `https://<host>:<WEB_PORT>/mcp_admin/config` 同样可达
4. UI 登录后左侧菜单出现「MCP服务器」，点开面板切一次端口验证自重启
5. 用「客户端配置」JSON 连接 MCP 客户端，`arl_ping` 返回 auth ok
6. 不带密钥请求 `<数据面>/mcp` 应 401

## 安全设计

- **文件沙箱**：AI 的所有文件增删改查 realpath 归一化后必须落在 `ARL_MCP_WORKSPACE` 内
  （穿越/软链/兄弟目录前缀混淆全拒绝）；临时文件只允许写 `<工作目录>/.tmp/`
- **接口白名单**：ARL 接口限 `/api/` 前缀；资产删除、查询集合有白名单
- **鉴权**：数据面强制 `X-API-Key` 请求头；管理面限内网来源
- **SSRF**：`fetch_url` 等工具参数 URL 仅 http/https，拒绝环回/私有/保留/CGNAT 地址，
  DNS 解析逐 IP 校验，重定向逐跳复检
- 传输层 Host/Origin 校验关闭（IP/端口在 UI 可变，无法枚举），由 API-Key 承担访问控制

## 测试与验证

```bash
python -m pytest tests/ -q                      # 48 项单元测试
python scripts/test_mcp_http.py                 # 端到端：鉴权/开关/数据读取/401
```

端到端回归覆盖：X-API-Key 正确/缺失/错误（401）、服务开关 403、
15 集合数据读取、6 组过滤参数、端口切换自重启链路。
