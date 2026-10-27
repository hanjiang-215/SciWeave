---
id: ai4-0uu6
status: closed
deps: []
links: []
created: 2026-10-27T03:01:35Z
type: feature
priority: 2
assignee: hanjiang
tags: [deployment, compose, infra]
---
# 演示链路最小容器编排

sci-weave/service 下只有 TerminusDB 与 Redpanda 两个第三方 compose；8 个业务服务各有一个 src/main.py、各自 .env 与端口，没有应用级 compose 或 Dockerfile。TECH_STACK.md 把生产部署、容器编排、密钥管理列为未确定项，并留了一条「各服务打一个镜像还是多容器」的待裁决问题。本票只解决演示链路能否一键起，不做生产形态。

## Design

最小形态：只编排演示链路所需的服务（research-map 及其 dashboard source、dashboard-api、可选 registry），复用已有 TerminusDB 与 Redpanda 服务。每个服务一个 Dockerfile，基于 python 镜像 + uv sync --locked；compose 用 env_file 注入，healthcheck 探测各自健康端点，网络与端口全部经环境变量配置，不写死。不做密钥管理方案，凭据仍旧走 .env，不入库。

## Acceptance Criteria

1) docker compose config 校验通过；2) 演示链路服务能 build 并 up，healthcheck 全部 healthy；3) 容器间通过服务名互访，不依赖宿主机回环；4) 启动后 dashboard-api 快照返回 mode=live；5) 不提交任何真实凭据，只提交 .env.example；6) 若构建因环境原因未能完成，如实记录卡点，不声称已通过；7) README 记录起停命令与端口。

## Notes

**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

新增：

- `sci-weave/demo-stack/`：`compose.yaml` + `README.md` + `.env.example`。按「多角色部署单元用项目组」的约定建成项目组，不承载源码。
- 三个 Dockerfile：`centre-control/research-map/`、`centre-control/dashboard-api/`、`centre-control/web-ui/`。前两者的构建上下文是 `centre-control`（research-map 通过 `[tool.uv.sources]` 依赖 `../shared/audit-trail`，uv 需要那条相对路径存在）；web-ui 用自己的目录作上下文。
- `centre-control/.dockerignore` 与 `centre-control/web-ui/.dockerignore`。

**TerminusDB 与 Redpanda 不重复定义**，按票内设计与既有约定复用 `sci-weave/service/<服务名>/` 的第三方服务，容器经 `host.docker.internal`（Linux 靠 `extra_hosts: host-gateway`）访问。

验证（本机 Docker 29.6.1 / Compose v5.1.4）：

```text
docker compose config --quiet           → 0
docker compose build                    → 三个镜像构建成功
docker compose ps                       → research-map / dashboard-api / web-ui 全 healthy
GET http://127.0.0.1:8702/api/dashboard/snapshot
  mode=live  partial=True  projects=1  tasks=3  events=1
  sources: mapping=fresh  wiki/gateway/queue=unavailable
  tasks: t1-v1 succeeded / t2-v1 succeeded / t3-v1 waiting
GET http://127.0.0.1:5173/              → 200，页面含 #app
CORS: Access-Control-Allow-Origin: http://127.0.0.1:5173
```

验收对照：

1. `docker compose config` 通过 ✓
2. 三个服务 build 并 up，healthcheck 全部 healthy ✓
3. 容器间经服务名互访（`dashboard-api` → `http://research-map:8701/api/dashboard/source/mapping`）✓
4. 快照 `mode=live` 且 `mapping=fresh`、3 个任务 ✓
5. 只提交 `.env.example`，未提交 `.env` 或真实凭据 ✓
6. 构建已完成，无环境卡点 ✓（受限网络的绕法见下）
7. README 记录起停命令、端口表与互访/跨域约束 ✓

过程中修掉三个真实缺陷：

- **`COPY . .` 覆盖依赖**：web-ui 镜像首次启动即 `Cannot find module '/app/node_modules/vite/bin/vite.js'`——构建上下文把宿主机 `node_modules` 复制进镜像，pnpm 的符号链接全部失效。加 `.dockerignore` 后重建正常。
- **播种脚本不幂等**：TerminusDB 12.0.8 对已存在的库返回 **400 + `api:DatabaseAlreadyExists`**（不是 409），脚本只容忍 409，于是「库已存在但容器卷是空的」时直接失败。改为识别该错误码并沿用已有库；compose 的 `seed` 服务默认带 `--reset`，让播种结果可复现。
- **基础镜像来源**：本机访问 `auth.docker.io` 超时，官方基础镜像拉不下来。三个 Dockerfile 都加了 `ARG PYTHON_IMAGE` / `ARG NODE_IMAGE`，用环境变量指向镜像代理即可构建——镜像源属于环境配置，没有写进仓库，README 记录了用法。

未验证项：只在 Windows + Docker Desktop 上跑过；`web-ui` 用 Vite dev server 而非静态构建（`VITE_DASHBOARD_API_URL` 是构建期变量，dev server 才能在运行时注入），生产形态的静态构建与注入方式未做，属 `docs/TECH_STACK.md` 里仍未决的部署形态问题。


