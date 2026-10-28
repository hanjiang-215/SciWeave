---
type: concept
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [deployment, docker, operations, infrastructure]
---

# 部署与运维

## 中央服务

`sci-weave/centre-stack/` 是中央服务器的正式部署单元：一个镜像、一个容器、supervisord 托管 12 个常驻进程角色。包含 Mapping/Wiki MCP 与看板来源、Draft Buffer、Registry、email-service、Centre Gateway MCP/subscriber、Coordinator、Dashboard API 和 Web UI 静态服务。Worker 不常驻，由 Gateway 以 multiprocessing 拉起。

中央容器使用具名卷 `centre-data` 挂载 `/data`，保存领域治理库、Registry、邮件投递、Coordinator、Gateway 会话和审计 SQLite。对外端口和令牌通过环境变量配置；MCP 使用 Bearer 鉴权，健康检查端点用于存活探测。

关键端口：Web UI `8080`、Dashboard API `8702`、Mapping MCP `8710`、Wiki MCP `8720`、Draft Buffer `8730`、Registry `8740`、Email `8750`、Gateway `8760`、Coordinator `8762`。部署到公网时，看板/API 应置于反向代理后，公网 TLS 尚未由仓库解决。

## 第三方基础设施

TerminusDB 与 Redpanda 位于 `sci-weave/service/<service>/`，各自有独立 Compose 和生命周期，不并入中央业务容器。TerminusDB 保存领域图快照和草稿；Redpanda 提供 Kafka API，传递治理事件和任务交接。

本地复用仓库 Redpanda 时，中央容器需要使用 `compose.local-redpanda.yaml`，让 Kafka advertised 地址在容器内可达。生产环境应配置容器可达的 advertised listener。

## 端侧与套件

- `researcher-agent-toolkit` 安装在研究员的 Agent 宿主，包含研究员技能、MCP 卡片和 Task Agent 部署 runtime。
- `project-owner-agent-toolkit` 安装在 Project Owner 的 harness，负责候选决策、影响预览和根任务派发。
- SciencePal 承载科研核心执行，不进入中央容器。

套件是可打包的目录，不是中央常驻服务；`centre-agent-toolkit` 已退场，Centre Agent 由中央容器部署。

## 演示栈

`sci-weave/demo-stack/` 只编排 Mapping 看板来源、Dashboard API、Vite Web UI 和一次性 seed。它用于一键演示和本地验证，不是生产部署形态，也不定义 TerminusDB/Redpanda。

## 验证入口

常用命令以各 README 和 `docs/验证命令.md` 为准：

```bash
# 中央第三方服务
docker compose -f sci-weave/service/terminusdb/compose.yaml up -d
docker compose -f sci-weave/service/redpanda/compose.yaml up -d

# 中央单容器
cd sci-weave/centre-stack
cp .env.example .env
docker compose --env-file .env up -d --build
docker compose --env-file .env run --rm bootstrap

docker compose --env-file .env ps
```

不要提交真实 `.env`、令牌、SMTP 密码、模型 Key、缓存、日志或构建产物。
