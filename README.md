# ARL-AI：ARL 资产侦察灯塔 + AI MCP

在 [yijingsec/ARL](https://gitee.com/yijingsec/ARL)（灯塔）上叠加 MCP 服务：
AI（ZCode / Claude 等）直接操作灯塔的任务与资产，灯塔 UI 注入两个栏目——
**MCP服务器**（开关/密钥/端口界面化管理）和**全局配置**（网页维护灯塔 FOFA/通知等配置）。

## 更新了什么

- **全局配置栏目**：像原生页面一样在灯塔 UI 里维护 `config.yaml`——
  FOFA（Email/Key/**baseurl，中转站账号改这里**）、GitHub Token、钉钉/飞书/企业微信通知、
  扫描代理、第三方测绘插件（Hunter/Quake/ZoomEye/VirusTotal 等 key + enable）。
  保存后点「重启服务生效」，自动按 scheduler → worker → web 顺序重启。
- **升级适应性**：老用户重跑脚本自动进升级模式——不停库不迁数据，保留原口令与 API 密钥
  （AI 客户端配置无感），前端缓存版本自动递增，已实测整机无损升级。
- **修复**：SSRF（`fetch_url` 锁定 IP 防 DNS Rebinding）、`arl_mcp` 专用账号防顶掉
  浏览器登录态、`pipefail`/CRLF 等升级链路隐患。

## 怎么搭建

先把仓库拉到目标服务器：

```bash
git clone https://github.com/AC-UVC/ARL-AI.git
cd ARL-AI/scripts/deploy
```

按你的情况对号入座（三选一）。**整个搭建过程可以直接交给 AI 辅助执行**——把本段命令
发给 ZCode / Claude 等客户端，它会按前置检查 → 部署 → 自检的顺序跑完并处理报错。

### 场景一：全新服务器（灯塔也没有）

`install.sh` 一键起整套灯塔 + MCP：

```bash
bash install.sh            # 默认 5003/5005/8010/8011，--web-port 等参数可自定义
```

脚本自动完成前置检查 → 拉镜像起容器组 → 注入前端/nginx → 装 MCP 服务 → 写 systemd →
自检 → 打印地址与回滚命令。装好后三步：灯塔 UI「MCP服务器」开服务并复制密钥 →
「全局配置」填 FOFA/通知等 → 重启服务生效。

### 场景二：已有原版灯塔（没装过 MCP，数据零拷贝，推荐）

```bash
bash overlay_install.sh --dir /opt/docker_arl --web-port 5003 \
     --web-container arl_web --mcp-port 8010 --admin-port 8011 \
     --public-ip <公网IP可选>
```

不新起灯塔、不碰数据库：compose 走 override 增量（原文件零改动）、前端/nginx 独立目录
挂载、只重建 web 容器（约 30 秒中断），worker/scheduler/数据库不动，进行中的扫描不受
影响；MCP 服务直连原灯塔 API，全部历史数据即刻可用。装好后同样三步。

### 场景三：已装上一版 ARL+MCP（升级）

**直接重跑同一个 overlay 命令**，新版自动进升级模式：

```bash
bash overlay_install.sh --dir /opt/docker_arl --web-port 5003 --web-container arl_web
```

- **保留**：原 arl_mcp 口令、API 密钥、服务开关与端口（AI 客户端配置不用改）
- **自动**：停止旧服务、覆盖安装、重启加载新代码（服务闪断几秒）、前端缓存版本递增
  （浏览器强刷一次看到新栏目）
- worker/scheduler 不动，进行中的扫描不受影响
- 提示：Windows 编辑过的 `*.sh` 推到 Linux 前确认 LF 行尾（仓库已配 `.gitattributes`）

## 效果预览
<img width="2560" height="1408" alt="image" src="https://github.com/user-attachments/assets/6db0e851-9447-40b1-88f1-b7b1ab84c45b" />

## 验证

```bash
python -m pytest tests/ -q          # 48 项单元测试
python scripts/test_mcp_http.py     # 端到端：鉴权/开关/数据读取/401
```

## 项目架构

```
arl_mcp/                     MCP 核心包：25 个工具、ARL API 客户端、文件沙箱、SSRF 防护
scripts/deploy/              部署脚本：overlay/一键安装、mcp_service.py（服务入口）、mcp_panel.js（前端注入）
tests/ + scripts/test_mcp_http.py    pytest 48 项 + 端到端回归
```

- **数据面**：FastMCP streamable-http（默认 8010），强制 `X-API-Key` 鉴权，服务开关/密钥/端口
  存 `mcp_config.json`
- **管理面**：固定 8011，来源限内网；MCP 自身管理之外，还提供 `config.yaml` 白名单读写
  与重启编排（全局配置的后端）
- **全局配置安全边界**：字段白名单（不碰 MONGO/CELERY/ARL.AUTH）、敏感值掩码不覆盖、
  配置容器动态发现三份同写、读取接口 30s 缓存
- 环境变量见 `mcp_service.py` 文件头（`ARL_URL`/`ARL_USER`/`ARL_PASS`、`ARL_MCP_WORKSPACE`、
  `MCP_PORT` 等十余项）
