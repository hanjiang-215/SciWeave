# SciWeave Dashboard API

为 Web 看板聚合多个领域服务提供的只读 JSON 快照。API 不访问或修改 Research Mapping、LLM-Wiki、Gateway、SQLite、TerminusDB、Redpanda、Agent 会话目录或队列 offset。

## 运行

本项目是独立 Python 子项目，使用 Python 3.11 及以上版本、uv 和标准库。将 `.env.example` 复制为本机 `.env`，配置监听地址和可用的只读来源 URL，然后执行：

```powershell
uv sync --locked
uv run --env-file .env python src/main.py
```

服务启动时输出实际绑定端口；`SCIWEAVE_DASHBOARD_PORT=0` 由操作系统分配临时端口，适用于本地验证。正式部署使用部署环境提供的地址与端口配置，不要把真实凭据写入仓库。

公开接口：

- `GET /health`：只返回服务状态和 API 版本。
- `GET /api/dashboard/snapshot`：聚合来源片段并返回统一看板快照。
- `OPTIONS /api/dashboard/snapshot`：仅在配置了 `SCIWEAVE_DASHBOARD_CORS_ORIGIN` 时提供受限跨源预检。
- `POST`、`PUT`、`PATCH`、`DELETE`：返回 `405 method_not_allowed`，不触发任何写入。

## 来源配置

所有地址、端口、超时、最大响应字节数和跨源来源都通过 `.env` 环境变量提供：

| 变量 | 用途 |
| --- | --- |
| `SCIWEAVE_DASHBOARD_HOST` | API 监听地址，必填 |
| `SCIWEAVE_DASHBOARD_PORT` | API 监听端口，必填；测试可用 `0` |
| `SCIWEAVE_DASHBOARD_SOURCE_TIMEOUT_SECONDS` | 每个来源请求超时秒数 |
| `SCIWEAVE_DASHBOARD_SOURCE_MAX_BYTES` | 单个来源最大响应大小 |
| `SCIWEAVE_DASHBOARD_CORS_ORIGIN` | 可选单一允许的浏览器来源，只接受 origin，不接受路径 |
| `SCIWEAVE_DASHBOARD_SOURCE_MAPPING_URL` | Research Mapping 只读快照地址 |
| `SCIWEAVE_DASHBOARD_SOURCE_MAPPING_TOKEN` | Mapping 来源的可选只读 Bearer 令牌，由服务端持有 |
| `SCIWEAVE_DASHBOARD_SOURCE_WIKI_URL` | LLM-Wiki 只读快照地址 |
| `SCIWEAVE_DASHBOARD_SOURCE_WIKI_TOKEN` | Wiki 来源的可选只读 Bearer 令牌，由服务端持有 |
| `SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_URL` | Gateway 只读执行与健康快照地址 |
| `SCIWEAVE_DASHBOARD_SOURCE_GATEWAY_TOKEN` | Gateway 来源的可选只读 Bearer 令牌，由服务端持有 |
| `SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL` | 消息监听状态只读快照地址 |
| `SCIWEAVE_DASHBOARD_SOURCE_QUEUE_TOKEN` | 消息监听来源的可选只读 Bearer 令牌，由服务端持有 |

来源地址必须是可信配置的 HTTP(S) URL，不能包含用户名或密码。未配置的来源保留为 `unavailable`，不被伪装成空数据；超时、非 2xx、非 JSON、超大响应和结构不符也分别形成安全的来源状态和摘要。异常正文、令牌、堆栈和路径不会透传给调用方。

该服务不实现用户身份系统。默认只绑定内部地址；对外部署必须放在受信任网络或具备认证的 HTTPS 反向代理之后。CORS 不是访问控制。浏览器端不应持有领域服务令牌或来源凭据；推荐同源部署，让反向代理承担用户认证与 TLS。

### 跨源部署（前端与 API 不同源）

浏览器将看板前端与 API 部署在不同源（不同主机、端口或协议）时，浏览器会先发 CORS 预检；此时必须把前端的确切 origin（例如 `https://dashboard.example.com`，只填 scheme://host[:port]，不带路径）配置到 `SCIWEAVE_DASHBOARD_CORS_ORIGIN`，否则预检不通过、请求被浏览器拦截，前端表现为持续报"数据服务暂时无法连接"。

- 该变量只接受**单一** origin，且只有请求 `Origin` 与之完全一致时才下发 `Access-Control-Allow-Origin`；未配置时不下发任何 CORS 头。
- 前端还需把 `VITE_DASHBOARD_API_URL` 指向 API 的可达基地址。
- 同源部署（通过反向代理把前端与 `/api` 放在同一源下）无需配置 CORS，是更推荐的方式。

## 来源片段契约

每个已配置来源通过 `GET <configured-url>` 返回一个 JSON 对象。`observedAt` 是来源采集时刻，采用包含时区的 ISO 8601 时间；`sourceStatus` 可为 `fresh`、`stale`、`partial` 或 `unavailable`；`freshUntil` 可选。聚合响应还包含 `mode: "live"`，用于防止前端把实时来源误认成本地演示数据。来源只填充自己负责的数组字段：

| 来源 | 允许提供的数据 |
| --- | --- |
| Research Mapping | `projects`、`tasks`、`events` |
| LLM-Wiki | `wikiDocuments`、`wikiCandidates`、`events` |
| Gateway | `executions`、`services`、`events` |
| 消息监听 | `services`、`events` |

示例：

```json
{
  "observedAt": "2026-10-22T09:30:00Z",
  "sourceStatus": "fresh",
  "freshUntil": "2026-10-22T09:35:00Z",
  "projects": [],
  "tasks": [],
  "events": []
}
```

来源响应不包含其他领域的数据，不返回私有存储内容。聚合器并行读取来源，保留每个来源的身份、状态和观测时间；部分来源失败时仍返回可用数据，并设置 `partial: true`。看板用的统一模型字段见 `../web-ui/src/domain/dashboard.ts`。

## 验证

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m compileall -q src tests
```

测试使用本机回环地址和系统分配的临时端口，不需要真实服务或凭据。所有上游边界都使用可替换读取函数验证聚合、超时和失败隔离。

## 依赖与许可

业务运行时仅使用 Python 标准库，不新增第三方运行时依赖。构建环境依赖 `setuptools==80.9.0`（PyPI，MIT 许可），仅用于 PEP 517 打包；构建版本固定在 `pyproject.toml`，运行依赖锁文件由 uv 管理。安装命令为 `uv sync --locked`；验证命令如上。
