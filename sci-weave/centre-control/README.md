# 中央服务器

`centre-control` 只表示这些内容部署在中央服务器。下面每个目录都是独立项目，不共用锁文件，也不作为一个部署单元一起启动。

| 目录 | 是什么 |
| --- | --- |
| `research-map` | Research Mapping，领域服务 + 管理 MCP 已实现 |
| `research-wiki` | LLM-Wiki，领域服务 + 管理 MCP 已实现 |
| `buffer` | 中央草稿箱，MCP 服务已实现（Streamable HTTP + stdio） |
| `centre-agents` | 中央协调 Agent；gateway/{ingest,mcp,subscriber} 与预审已实现 |
| `coordinator` | 交接协调器：治理事件 → 正式快照 → `task_handoff_ready` 派发，含依赖重算、执行者选择、重试上限与启动恢复 |
| `registry` | 主体与端侧 Agent 的登记表，已实现（见 `registry/README.md`） |
| `email-service` | 人工通知投递：真实 SMTP 发送端口、收件人解析、逐收件人重试与错误分类，MCP 已实现 |
| `dashboard-api` | Web 看板只读聚合 API，已实现 |
| `web-ui` | Web 看板前端，已实现 |
| `shared/audit-trail` | 中央留痕工具，接口层调用账本；多个中央项目共用的代码，不是独立部署单元 |
| `shared/message-envelope` | 消息信封协议包（schema、JSON 编解码、四类错误区分）；**当前无生产调用方**，接线决策见 `ai4-4bxp` |

`shared/` 是**代码归属边界**，不是项目组：这里的代码被至少两个中央项目以 uv path 依赖引用，不产生组级 `pyproject.toml` 或组级 `uv.lock`，各调用方各自提交锁文件。

第三方服务容器（TerminusDB、Redpanda）不在这里，放在 `sci-weave/service/<服务名>/`：它们是本地验证用的独立服务，与中央业务项目分属不同的部署单元。
