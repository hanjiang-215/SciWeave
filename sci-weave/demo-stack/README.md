# demo-stack

把**演示链路**的三个进程角色编排起来：research-map 的看板来源、dashboard-api、web-ui。

它只解决「一键起得来」，不是生产形态。生产部署、密钥管理仍是 `docs/TECH_STACK.md` 里的未确定项。

## 它编排什么、不编排什么

| 服务 | 角色 | 镜像来源 |
| --- | --- | --- |
| `research-map` | 看板来源，只读投影正式路线 | `centre-control/research-map/Dockerfile` |
| `dashboard-api` | 多来源聚合，输出 `/api/dashboard/snapshot` | `centre-control/dashboard-api/Dockerfile` |
| `web-ui` | Vite dev server，浏览器看板 | `centre-control/web-ui/Dockerfile` |
| `seed`（profile） | 一次性播种演示域，不常驻 | 复用 research-map 镜像 |

**不在这里定义 TerminusDB 与 Redpanda**。它们是第三方服务，按约定留在 `sci-weave/service/<服务名>/`，本栈按宿主机地址复用。这与 `ai4-0uu6` 的设计一致。

## 前置条件

1. Docker 与 `docker compose`（本机验证版本：Docker 29.6.1 / Compose v5.1.4）。
2. 宿主机上 TerminusDB 已起：

   ```bash
   docker compose -f sci-weave/service/terminusdb/compose.yaml up -d
   ```

3. 复制环境变量样例：

   ```bash
   cp sci-weave/demo-stack/.env.example sci-weave/demo-stack/.env
   ```

## 起停

```bash
cd sci-weave/demo-stack

# 构建并启动
docker compose up -d --build

# 播种演示域（容器卷与 TerminusDB 两侧一起重建，结果可复现）
docker compose --profile seed run --rm seed

# 查看状态（healthcheck 全 healthy 才算起来）
docker compose ps

# 停（加 -v 连同播种数据一起删）
docker compose down
```

`seed` 默认带 `--reset`：它会删除并重建 TerminusDB 里的演示库。这是刻意的——播种要可复现，否则「库已存在但本地卷是空的」这种半截状态会让人以为看板坏了。

## 端口

| 端口 | 服务 | 说明 |
| --- | --- | --- |
| 8701 | research-map | 看板来源：`/health`、`/api/dashboard/source/mapping` |
| 8702 | dashboard-api | 聚合：`/health`、`/api/dashboard/snapshot` |
| 5173 | web-ui | 看板页面 |

全部经环境变量配置（`MAPPING_HOST_PORT` / `DASHBOARD_HOST_PORT` / `WEB_HOST_PORT`），不写死在代码里。

## 互访与跨域

- 容器之间走**服务名**：`dashboard-api` 用 `http://research-map:8701/...` 取数，不经宿主机回环。
- 浏览器跑在宿主机上，所以 `VITE_DASHBOARD_API_URL` 与 `SCIWEAVE_DASHBOARD_CORS_ORIGIN` 都必须是**宿主机视角**的地址。两处配错是「页面空白 / 请求被 CORS 拦」的常见原因。
- 容器访问宿主机的 TerminusDB 走 `host.docker.internal`，Linux 上靠 `extra_hosts: host-gateway` 才通。

## 验证

```bash
# 配置语法
docker compose config --quiet

# 快照是否为真实数据
curl -s http://127.0.0.1:8702/api/dashboard/snapshot
```

期望 `mode=live`，`sources` 中 `mapping=fresh`，`tasks` 非空。

## 为什么 web-ui 用 dev server

`VITE_DASHBOARD_API_URL` 是 Vite 的构建期变量。跑 dev server 时它可以在运行时注入，同一个镜像能指向不同 dashboard-api；烤进 `dist` 就得为每个环境重新构建。生产形态需要另行决定静态构建与注入方式，不在本栈范围。

## 受限网络下构建

三个 Dockerfile 的基础镜像都留了 `ARG`（`PYTHON_IMAGE` / `NODE_IMAGE`），默认指向 Docker Hub 官方地址。拉不动官方地址时，用环境变量把它指到本地可用的镜像代理即可，**不要把这个地址写进仓库**：

```bash
export PYTHON_IMAGE=docker.1ms.run/library/python:3.13-slim
export NODE_IMAGE=docker.1ms.run/library/node:22-slim
docker compose build
```

本次验证就是这么构建的：本机访问 `auth.docker.io` 超时，改用镜像代理后三个镜像均构建成功。

## 凭据

只提交 `.env.example`，`.env` 不入库。示例里的 `root` 是本机固定 TerminusDB 容器的默认口令，换成真实实例时必须改，且不要把真实值写进仓库。
