# SciWeave 中央服务单容器部署

把 `sci-weave/centre-control` 下**所有**中央服务打进一个镜像、用一个容器跑起来的部署单元：一个 `Dockerfile` + 一个 `compose.yaml` + 一份 `supervisord.conf`。12 个进程角色全部由容器内的 supervisord 托管。

> 这是 `docs/TECH_STACK.md` 里「centre-control 是否打成一个镜像、单容器多进程」那条待裁决问题的落地形态，决策记录见 [`docs/adr/0006-centre-single-container.md`](../../docs/adr/0006-centre-single-container.md)。

## 部署拓扑

| 层 | 承载 | 部署位置 |
| --- | --- | --- |
| 中央服务 | 领域治理 MCP、草稿箱、Registry、协调器、通知、看板 | **本目录一个容器**（部署在中央服务器） |
| 端侧套件 | `sci-weave/toolkits/`（runtime / service-template / sciencepal-bridge） | WorkBuddy / DSH 上的 Agent 宿主 |
| 科研核心 | SciencePal 上的 Iris T1/T2 执行 | SciencePal 沙箱 |

端侧套件与 SciencePal 通过本容器暴露的 MCP 端口（Bearer 令牌）访问中央治理能力，不需要也不应该进这个容器。

第三方服务 **TerminusDB** 与 **Redpanda** 不在这里重复定义，按既有约定跑在 `sci-weave/service/<服务名>/`，默认经宿主机地址访问：

```powershell
docker compose -f sci-weave/service/terminusdb/compose.yaml up -d
docker compose -f sci-weave/service/redpanda/compose.yaml up -d
```

容器内通过 `host.docker.internal` 连宿主机上的它们（Linux 上由 compose 的 `extra_hosts: host-gateway` 保证）。

## 快速开始

```powershell
cd sci-weave/centre-stack

# 1. 生成真实令牌（占位令牌会让任何知道 .env.example 的人拿到管理接口）
#    把输出粘进 .env 对应位置
python -c "import secrets;print('\n'.join(f'{n}={secrets.token_urlsafe(24)}' for n in [
  'CENTRE_TOKEN_MAP_AGENT','CENTRE_TOKEN_MAP_OWNER','CENTRE_TOKEN_WIKI_AGENT',
  'CENTRE_TOKEN_WIKI_OWNER','CENTRE_TOKEN_CENTRE_AGENT','CENTRE_TOKEN_BUFFER',
  'CENTRE_TOKEN_REGISTRY_OWNER','CENTRE_TOKEN_REGISTRY_RESEARCHER',
  'CENTRE_TOKEN_REGISTRY_CENTRE','CENTRE_TOKEN_REGISTRY_EMAIL',
  'CENTRE_TOKEN_EMAIL_WORKFLOW','CENTRE_TOKEN_EMAIL_OPS',
  'CENTRE_TOKEN_COORDINATOR','CENTRE_TOKEN_GATEWAY','CENTRE_TOKEN_DASHBOARD_SOURCE']))"

# 2. 复制并填写
Copy-Item .env.example .env
#   编辑 .env：粘令牌、改 SCIWEAVE_EMAIL_FROM_ADDRESS、按需改公网地址

# 3. 构建并启动（首次构建较久：要同步 9 个 uv 项目并构建前端）
docker compose --env-file .env up -d --build

# 4. 建好三个领域库（幂等；不做这一步草稿箱会 FATAL、看板的 mapping/wiki 来源恒 unavailable）
docker compose --env-file .env run --rm bootstrap

# 5. 观察
docker compose --env-file .env logs -f
docker compose --env-file .env ps
```

> `env_file: .env` 声明为 `required: false`：没建 `.env` 也能 `config`/`build`，但 `up` 会在必填令牌处报错，指明缺哪个变量。统一用 `--env-file .env` 是为了让 compose 插值也读到真实令牌。

### 复用仓库自带 Redpanda 时（本地）

`sci-weave/service/redpanda/compose.yaml` 把 external 监听 advertise 成 `localhost:19092`。容器里的 `localhost` 是容器自己，Kafka 客户端拿到这份元数据后会连自己的 19092，coordinator 随即连不上并退出。用附带的覆盖文件让容器接入 Redpanda 的 docker 网络、改走内网监听：

```powershell
docker compose --env-file .env -f compose.yaml -f compose.local-redpanda.yaml up -d
```

生产环境不需要这个文件：给 broker 配上容器可达的 `advertised.listeners`，并把 `SCIWEAVE_CENTRE_KAFKA_BOOTSTRAP` 指过去即可。

### 没有模型密钥时的 subscriber

`centre-gateway-subscriber` 在 `DEEPSEEK_API_KEY` 为空且未显式开 passthrough 时会**拒绝启动**（`FATAL`，日志 `no Worker runtime: ...`）。这是既有设计：宁可明确失败，也不写桩历史冒充执行结果。三种选择：

- 在 `.env` 里配 `DEEPSEEK_API_KEY`（真实执行）；
- 只做链路演示时设 `SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1`（明确标注：写桩历史，不调模型）；
- 暂不使用队列消费，此时 `queue` 看板来源为 `unavailable`，其余 11 个角色不受影响。

## 访问路径

对外发布的端口（宿主机视角）。浏览器/端侧 Agent 用下面这些：

| 服务 | 对外端口 | 路径 | 鉴权 |
| --- | --- | --- | --- |
| **Web 看板**（浏览器） | `8080` | `http://<host>:8080/`（SPA，深链接回退 index.html） | 无（部署时置于反代后） |
| **Dashboard API** | `8702` | `GET /api/dashboard/snapshot`、`GET /health` | 无（只读聚合，部署时置于反代后） |
| **Research Mapping 管理 MCP** | `8710` | `POST /mcp`（JSON-RPC）、`GET /health` | Bearer 令牌 |
| **Research Wiki 管理 MCP** | `8720` | `POST /mcp`、`GET /health` | Bearer 令牌 |
| **草稿箱 MCP** | `8730` | `POST /mcp`、`GET /health` | Bearer 令牌 |
| **Registry MCP** | `8740` | `POST /mcp`、`GET /health` | Bearer 令牌 |
| **email-service MCP** | `8750` | `POST /mcp`、`GET /health` | Bearer 令牌 |
| **中央 Agent Gateway MCP** | `8760` | `POST /mcp`、`GET /health`、`GET /sources` | Bearer 令牌（`/sources` 同） |
| **coordinator MCP** | `8762` | `POST /mcp`（`dispatch_root_task`）、`GET /health` | Bearer 令牌 |

容器内部（不对外发布，仅供容器内互访）的端口：`8711` mapping 看板来源、`8721` wiki 看板来源、`8761` 队列看板来源。看板 API 通过容器内回环读这三个来源。

> 各端口可用 `CENTRE_*_HOST_PORT` 环境变量改宿主机映射，例如 `CENTRE_WEB_UI_HOST_PORT=80`、`CENTRE_MAPPING_MCP_HOST_PORT=8710`。改端口后记得同步改 `.env` 里的 `SCIWEAVE_CENTRE_PUBLIC_ORIGIN` 与构建参数 `VITE_DASHBOARD_API_URL`。

## 容器内进程（supervisord 托管）

```text
program:registry            → /opt/venvs/registry/bin/python src/main.py        :8740
program:email-service       → /opt/venvs/email-service/bin/python src/main.py   :8750
program:mapping-mcp         → research-map src/main.py（MCP 模式）              :8710
program:mapping-dashboard   → research-map src/main.py（看板模式）              :8711
program:wiki-mcp            → research-wiki src/main.py（MCP 模式）             :8720
program:wiki-dashboard      → research-wiki src/main.py（看板模式）             :8721
program:draft-buffer        → buffer src/main.py（Streamable HTTP）             :8730
program:centre-gateway-mcp  → sciweave-task-agent-gateway-mcp                   :8760
program:centre-gateway-subscriber → sciweave-task-agent-gateway-subscriber      :8761（看板子端点）
program:coordinator         → coordinator src/main.py（Kafka 消费 + MCP）       :8762
program:dashboard-api       → dashboard-api src/main.py                         :8702
program:web-ui-static       → serve_web_ui.py（静态托管 /app/web-ui/dist）      :8080
```

`research-map` / `research-wiki` 的 `src/main.py` 是单进程入口，同一进程不能同时跑看板和 MCP，所以各拆成两个 program，用 `SCIWEAVE_MAPPING_DASHBOARD_MODE` / `SCIWEAVE_WIKI_DASHBOARD_MODE` 区分。`centre-agents/worker` 不是常驻角色（由 gateway 用 multiprocessing 子进程拉起），不单独托管。

查看/重启单个角色：

```bash
docker compose --env-file .env exec centre supervisorctl status
docker compose --env-file .env exec centre supervisorctl restart mapping-mcp
docker compose --env-file .env exec centre supervisorctl tail -f coordinator stderr
```

## 令牌与凭据要求

- 所有令牌、SMTP 密码、DeepSeek Key 只存在宿主机 `.env`（已 gitignore），**不得提交**。仓库只提交 `.env.example`。
- compose 对每个必填令牌用 `${VAR:?}` 失败关闭：缺哪个、哪个没填，`up` 直接报错，不会用可猜的默认令牌把管理接口暴露出去。
- **SMTP 是「要么全配、要么全空」**：`.env` 里给了 `SCIWEAVE_EMAIL_SMTP_HOST` 就必须同时给 PORT/USERNAME/PASSWORD/SECURITY，只配一半会让 email-service 拒绝启动（防止密码在 starttls 之前明文送出）。全空时服务照常提供状态查询，`/health` 报 `not_configured`。
- `SCIWEAVE_EMAIL_SMTP_SECURITY` 必填且无默认值：`ssl` / `starttls` / `none`。

## 能力档（写进 compose 的默认值）

| actor | 能力 |
| --- | --- |
| `map-agent` / `wiki-agent` | `read` + `candidate_submit`（端侧 Agent 提交候选） |
| `map-owner` / `wiki-owner` | `read` + `candidate_review` + `formalize`（PO 审核与正式化） |
| `centre-agent` | `centre` + `prereview_log` + `merged_candidate`（中央 Agent 预审与合并） |

`centre` 只解锁 4 个读工具，不授予任何写工具；`formalize` 做 Owner 批准时，批准人与被批准人都要持有该能力。能力表在 `compose.yaml` 的 `SCIWEAVE_MAPPING_CALLER_CAPABILITIES_JSON` / `SCIWEAVE_WIKI_CALLER_CAPABILITIES_JSON` 里维护。

## 健康检查

- 容器级 `HEALTHCHECK` 只看 `dashboard-api`（`/health` 不依赖 TerminusDB 就能回 ready，适合做存活探针）。
- 每个角色的就绪状态用 `supervisorctl status` 观察；HTTP 探针：

```bash
# 容器外
curl -f http://<host>:8702/health
curl -f -H "Authorization: Bearer <token>" http://<host>:8710/health   # MCP 端点 health 无需令牌
```

> `/health` 是纯存活探针，不探测 TerminusDB 可达性。业务可用性看看板快照 `GET /api/dashboard/snapshot` 里各来源的 `status`（`fresh`/`unavailable`）。

## 数据与持久化

具名卷 `centre-data`（可 `CENTRE_DATA_VOLUME` 改名）挂到 `/data`，全部 SQLite 与会话文件都落在这里：

| 路径 | 归属 |
| --- | --- |
| `/data/mapping/` | research-map 治理库与审计 |
| `/data/wiki/` | research-wiki 治理库与审计 |
| `/data/registry/` | Registry 库 |
| `/data/email/` | email 投递库 |
| `/data/coordinator/` | coordinator 状态库 |
| `/data/centre-agents/` | Gateway 共享 SQLite + worker 会话 |
| `/data/audit/` | 各服务审计账本 |

审计账本默认每服务一个文件（单容器里避免多进程争写同一 SQLite）；要合成一份账本就统一 `SCIWEAVE_*_AUDIT_SQLITE_PATH` 指向同一路径（审计库用 WAL + busy_timeout，会串行化写入）。

## 构建参数与受限网络

| ARG | 默认 | 用途 |
| --- | --- | --- |
| `PYTHON_IMAGE` | `python:3.13-slim` | 基础镜像，可指向镜像代理 |
| `NODE_IMAGE` | `node:22-slim` | 前端构建镜像 |
| `VITE_DASHBOARD_API_URL` | `http://127.0.0.1:8702/` | 前端 bundle 里 dashboard-api 的绝对地址 |

`VITE_DASHBOARD_API_URL` 是构建期变量：部署到服务器后，改 `.env` 里这一项并重新 `--build`，前端才会指向真实地址。它必须与 `SCIWEAVE_CENTRE_PUBLIC_ORIGIN`（CORS 来源）是同一台服务器视角。

镜像内不保留 uv、Node 或任何 dev 依赖：uv 只在构建期同步依赖后删除，前端产物是静态构建，运行时只有 Python + supervisord。

## 验证

```powershell
# compose 配置校验（不需要 .env 也能跑）
docker compose --env-file .env.example config --quiet

# 构建并启动（需要 TerminusDB + Redpanda 已就绪）
docker compose --env-file .env up -d --build
docker compose --env-file .env run --rm bootstrap
docker compose --env-file .env ps
```

本机实测记录（2026-10-27，Docker 29.6.1 / Compose v5.1.4，Windows + Docker Desktop）：

```text
docker compose config --quiet                     → 0
docker compose build                              → sciweave/centre:local 构建成功
docker compose run --rm bootstrap                 → 三个库 created
容器启动 20s 内 healthy
supervisorctl status                              → 11 RUNNING / 1 FATAL（subscriber，缺模型密钥，设计如此）
GET :8080/health                                  → 200
GET :8702/health                                  → 200
GET :8710/health / :8720/health / :8730/health    → 200（MCP）
GET :8740/health / :8762/health                   → 200
GET :8750/health                                  → 503（SMTP 未配置，email-service 仍提供状态查询）
GET :8760/health                                  → 200
GET :8702/api/dashboard/snapshot                  → mode=live，gateway 来源 fresh；
                                                    mapping/wiki 因新库尚无正式版本报 unavailable（正确语义），
                                                    queue 因 subscriber 未运行报 unavailable
```

看板自检：浏览器打开 `http://<host>:8080/`。空库时页面为空但四个来源状态可见；播种后 `mapping` 会变 `fresh`。

日志：12 个角色的 stdout/stderr 都进容器日志（`docker logs -f sciweave-centre`），也可按角色看 ——

```bash
docker compose --env-file .env exec centre supervisorctl tail -f coordinator stderr
```

## 已知缺口（不属于本单元范围）

- `research-wiki` 的正式化**不发布治理事件**（`WikiManagementService` 无治理事件端口），wiki 候选的治理闭环依赖 Centre Agent 的快照扫描而非事件推送。见 `docs/AI4Sci-review-2026-10-27.md` 与工单记录。
- `SCIWEAVE_MAPPING_KAFKA_BOOTSTRAP` 曾在 `research-map` 的 config 里被读取后丢弃（治理事件恒为 Noop），本轮已修复并补回归测试（`ai4-e1jk`）。
- 公网暴露的 TLS 与反向代理不在本单元内；MCP 端点已有 Bearer 鉴权，看板与 Dashboard API 建议置于反代之后。
- coordinator 在 Kafka 短暂不可达时会被异常打断并由 supervisord 重启（不是静默丢事件，但会表现为 FATAL 重试循环），排障时先看 `redpanda` 是否可达。
