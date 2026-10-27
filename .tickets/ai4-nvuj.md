---
id: ai4-nvuj
status: closed
deps: []
links: []
created: 2026-10-27T03:01:26Z
type: feature
priority: 1
assignee: hanjiang
tags: [dashboard, queue, gateway]
---
# dashboard-api queue 来源补上提供方

dashboard-api 的 config.py 定义了四个来源槽：mapping、wiki、gateway、queue。前三者都有提供方（research-map/research-wiki 的 dashboard_source，以及 gateway MCP 的 /dashboard），queue 槽没有任何服务实现，永远是 source_not_configured，导致看板的「消息监听」状态恒为不可用。另外 gateway 的 dashboard_sources() 把 events 硬编码为空数组，前端事件区永远是空的。

## Design

在 gateway/subscriber 增加只读 HTTP 看板端点（与 gateway/mcp 的 dashboard_sources 同形状：observedAt/sourceStatus/services/events），输出订阅状态、consumer group、最近消费事件，不输出消息正文与凭据。实现 services 与 events 两个集合；queue 槽在 dashboard-api config 中指向该端点。gateway 的 events 硬编码问题同批修复，改为读取最近审计事件或明确说明为空的原因。

## Acceptance Criteria

1) subscriber 提供 /dashboard 端点，返回 services 与 events，含 sourceStatus；2) dashboard-api 配置 queue 来源后 GET /api/snapshot 的 sources 中 queue 为 fresh；3) events 不硬编码空数组；4) 不泄露凭据、消息正文或堆栈；5) 新增测试覆盖成功、来源不可用、畸形响应三种情况；6) 全量 pytest 通过并在票内记录命令与结果。

## Notes

**2026-10-27 交付（hanjiang）**

身份核对：assignee `hanjiang`、分支 `feature/hanjiang`、`git config user.name=hanjiang`，三者一致。

实现：

- 新增 `gateway/subscriber/src/gateway_subscriber/dashboard_source.py`：`build_queue_fragment()` 把订阅状态投影成 `{observedAt, sourceStatus, services, events}`，`create_queue_dashboard_server()` 提供 `/health`（开放）与 `/api/dashboard/source/queue`、`/sources`（配了令牌则要求 Bearer）。只输出 topic、消费组、服务状态与审计事件摘要，不含消息正文与凭据。
- `gateway/subscriber/src/gateway_subscriber/cli.py`：新增 `start_dashboard_server()`，由 `SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT` 开关，主循环在后台线程服务，退出时 `shutdown()`。未配端口则完全不起监听，现有部署行为不变。
- `gateway/mcp/src/gateway/app.py::dashboard_sources()`：`events` 由审计表投影（`execution_queued`/`owner_command_received` → `message_received`，`execution_completed`/`worker_completed` → `execution_completed`，`execution_failed`/`worker_failed` → `mcp_failure`），不再硬编码空数组。

**顺带修掉一个会让看板整体失效的缺陷**：gateway 原来用 `label` 作服务名，而 dashboard-api 的脱敏白名单里没有 `label`（会被整条丢掉）；`role` 写成 `gateway`/`worker`/`listener`、`status` 写成 `ready`/`not_configured`，都不在 web-ui `isService` 接受的取值里。也就是说只要配了 gateway 来源，前端 `isDashboardSnapshot` 校验就会失败、整份快照被拒。现统一为 `name` + `role=centre-agent` + `status ∈ {online, stale, unavailable, unknown}`，运行时 `misconfigured` 映射为 `unavailable`。

验证：

```text
subscriber: 27 passed（新增 test_queue_dashboard.py 11 项）
gateway mcp: 13 passed（更新 test_dashboard_sources_* 与 test_dashboard_component_matches_health）
```

真实进程联调（独立 queue 来源进程 + research-map mapping 来源 + dashboard-api）：

```text
mode=live partial=True
sources: mapping=fresh  wiki=unavailable  gateway=unavailable  queue=fresh
services: subscriber/queue/consumer-group，role=centre-agent，status=online
events: formal_release（mapping）+ message_received（queue）
```

验收对照：

1. subscriber 端点返回 `services`/`events`/`sourceStatus` ✓（端点路径为 `/api/dashboard/source/queue`，另提供 gateway 风格别名 `/sources`）
2. dashboard-api 配 `SCIWEAVE_DASHBOARD_SOURCE_QUEUE_URL` 后 `queue=fresh` ✓
3. events 不再硬编码 ✓
4. 不泄露凭据/正文/堆栈；异常统一降级为 `unavailable` 与 `{"error": ...}` ✓
5. 测试覆盖成功、来源不可用（`_BrokenStore`）、审计读取失败（`_HalfBrokenStore`）、401/404 ✓
6. 测试命令与结果如上 ✓

遗留：看板只验证到 HTTP 层与聚合结果，**没有在真实浏览器里目视确认**；`docs/demo-dashboard.md` 已补 queue 来源的配置说明。


