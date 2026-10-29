# dsh/ —— 本地一键运行 centre-control 全部服务

把 `sci-weave/centre-control` 下的 12 个进程角色在**本机**跑起来（不走 Docker 打镜像）。
脚本的编排依据是 `sci-weave/centre-stack` 里的 `Dockerfile` / `supervisord.conf` / `compose.yaml`：
那份配置定义了「同一份环境 + 12 个角色各自的工作目录、入口与端口」，这里把它翻译成本机进程。

## 前置

- `uv`（各子项目已有 `.venv` 与 `uv.lock`；没装过就先在对应目录 `uv sync`）
- Node.js（`web-ui/node_modules` 已安装；否则 `cd sci-weave/centre-control/web-ui && pnpm install`）
- **Docker Desktop 已启动**：TerminusDB 与 Redpanda 是第三方依赖，仍用 `sci-weave/service/` 的 compose 起

## 用法

```powershell
# 全量启动（含 TerminusDB/Redpanda + 建库 + 12 角色 + 前端）
pwsh -File dsh/start.ps1

# 已有 TerminusDB/Redpanda，跳过它们
pwsh -File dsh/start.ps1 -SkipDocker

# 不启动前端
pwsh -File dsh/start.ps1 -SkipWeb

# 停止
pwsh -File dsh/stop.ps1
# 连第三方服务一起停
pwsh -File dsh/stop.ps1 -StopDocker
```

首次运行会自动：

1. 从 `.env.example` 生成 `dsh/.env`，并把所有 `change-me-*` 令牌换成随机值；
2. 用 Docker 起 TerminusDB（:6363）与 Redpanda（:19092）；
3. 复用 `sci-weave/centre-stack/scripts/bootstrap_terminusdb.py` 建好三个领域库（幂等）；
4. 用各子项目 `.venv` 拉起 12 个角色，pid 记录在 `dsh/pids/`，日志在 `dsh/logs/`，数据在 `dsh/data/`；
5. 启动前端 vite dev。

## 访问地址

| 服务 | 地址 |
| --- | --- |
| 看板前端 | http://127.0.0.1:5173/ |
| 看板 API | http://127.0.0.1:8702/health |
| Research Mapping MCP | http://127.0.0.1:8710/mcp（Bearer） |
| Research Wiki MCP | http://127.0.0.1:8720/mcp（Bearer） |
| 草稿箱 MCP | http://127.0.0.1:8730/mcp（Bearer） |
| Registry MCP | http://127.0.0.1:8740/mcp（Bearer） |
| email-service MCP | http://127.0.0.1:8750/mcp（Bearer） |
| Gateway MCP | http://127.0.0.1:8760/mcp（Bearer） |
| coordinator MCP | http://127.0.0.1:8762/mcp（Bearer） |

令牌在 `dsh/.env`（不提交）。

## 角色与入口对照

| 角色 | 目录 | 入口 |
| --- | --- | --- |
| mapping-mcp / mapping-dashboard | research-map | `src/main.py`（`SCIWEAVE_MAPPING_DASHBOARD_MODE` 区分） |
| wiki-mcp / wiki-dashboard | research-wiki | `src/main.py`（`SCIWEAVE_WIKI_DASHBOARD_MODE` 区分） |
| draft-buffer | buffer | `src/main.py` |
| registry | registry | `src/main.py` |
| email-service | email-service | `src/main.py` |
| coordinator | coordinator | `src/main.py` |
| centre-gateway-mcp / -subscriber | centre-agents | `.venv/Scripts/sciweave-task-agent-gateway-*.exe` |
| dashboard-api | dashboard-api | `src/main.py` |
| web-ui | web-ui | `vite`（dev） |

## 与 Docker 版的差异

- 数据目录 `/data` → `dsh/data/`；容器路径 `/app/...` → 仓库内实际路径；
- 第三方服务地址 `host.docker.internal` → `127.0.0.1`；
- 前端用 vite dev（5173）而非容器内静态托管（8080），`SCIWEAVE_CENTRE_PUBLIC_ORIGIN` 相应为 `http://127.0.0.1:5173`。

## 已知取舍

- subscriber 在没有 `DEEPSEEK_API_KEY` 且未设置 `SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1` 时按设计拒绝启动（`FATAL`），队列看板来源显示 `unavailable`；其余角色不受影响。要在本地真正跑模型执行，在 `dsh/.env` 里配 `DEEPSEEK_API_KEY`。
- SMTP 要么全配、要么全空；全空时 email-service 记为 `not_configured`，仍提供状态查询。
