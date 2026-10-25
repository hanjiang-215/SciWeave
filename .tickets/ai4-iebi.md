---
id: ai4-iebi
status: closed
deps: []
links: [ai4-f985, ai4-m1d1, ai4-ced7, ai4-te1v]
created: 2026-10-25T09:13:37Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-f985
tags: [implementation, task-agent, mcp, email-service, notification, ready-for-agent]
---
# 端侧 Task Agent 接入 email-service MCP 并登记标准卡片

把中央 `email-service` 作为端侧 Task Agent 可直接调用的标准 MCP 资源接入：在 `libs/mcp-libs` 登记 `email-service` 卡片，在端侧 `.env.example` 声明地址与令牌，并修正 `get_notification_status` 被当作写调用的审计标记。

## Design

**通道决定：MCP 直连，不经消息队列。** 端侧 Task Agent 直接调用中央 `email-service` 的受鉴权 MCP 工具 `send_notification`；不使用 `sciweave.notification-intent` topic。依据 `ai4-f985` 已定的「首版 MCP 是唯一输入入口，不消费 Redpanda 通知 topic」。`human_notification_intent` 保持不变，仍是 MCP 请求与投递记录的业务对象，只是承载方式由队列消息改为一次工具调用。

**卡片位置。** 放标准目录 `libs/mcp-libs/email-service/mcp.json`，与 `research-mapping`、`research-wiki`、`draft-buffer` 同级，因为 email-service 是平台提供的中央服务；`local-mcp-libs` 只留给研究员自建的本地服务。

**工具面。** 卡片只暴露 `send_notification` 与 `get_notification_status`，不暴露 `health`。发完能确认投递结果属于业务需要；`health` 是运维探测，进 Agent 工具面会被误当业务信号。

**令牌模型。** 每个中央 MCP 各自维护一份 token 表，一个 token 只对一个服务有效。端侧 `.env` 需要为 mapping、wiki、buffer、email 各存一个不同的 token。email 的 token 条目落在 `SCIWEAVE_EMAIL_TOKENS_JSON`，`caller_id` 按研究员个人签发（`person:<principal_id>`，`caller_type=researcher`），因为 `get_notification_status` 的可见性是 `caller_id` 相等才放行；共用一个 `service:` 身份会让所有研究员的投递状态混成一个可见域。

**地址形态。** `EMAIL_MCP_URL` 必须写到 `/mcp` 路径（`http://<host>:<port>/mcp`）。四个服务的 Streamable HTTP 端点都只在 `POST /mcp` 响应。

**审计修正。** `get_notification_status` 是读工具，但被标记为 `write=True`，走两阶段 fail-closed 审计并先写 `invoked`。改为 `write=False`（单阶段 `attempted` fail-open），与仓库「读 fail-open、写 fail-closed」的约定一致；不修会让审计库不可用时读状态被阻断。

**不做的部分。** 不接真实 `RecipientResolver` 的 Registry 适配器（另票，依赖 Registry 实现）；不在 `work_agent_runtime` 里加 MCP 客户端（端侧运行时接入另行推进）；不改 `email-service` 的 `notification_kind` 集合，现有 13 个核心类型已覆盖端侧全部已知场景且对所有已认证调用方开放。

## Acceptance Criteria

- [x] `libs/mcp-libs/email-service/mcp.json` 存在，`transport=streamable-http`，`endpoint.url_env=EMAIL_MCP_URL`，`environment` 含 URL 与 TOKEN 两项。
- [x] 卡片工具面恰为 `send_notification` 与 `get_notification_status`，两者的必填参数与 `email-service` 实际工具定义逐项一致。
- [x] 卡片的 `failures` 列出全部可观察错误码，并对尚未接真实 Registry 的 `recipient_resolver_unavailable` 标注其为临时错误。
- [x] 端侧 `.env.example` 声明 `EMAIL_MCP_URL` 与 `EMAIL_MCP_TOKEN`，并说明 URL 需带 `/mcp` 路径、token 来自 email-service 自己的令牌表。
- [x] `get_notification_status` 的审计标记改为读语义，并由测试断言其账本记录为 `attempted` 阶段。
- [x] 起真实 `email-service` 服务，用 `mcp` 客户端完成 `initialize`、`tools/list`、一次 `send_notification` 与一次 `get_notification_status`；收件人使用 Fake resolver。
- [x] `email-service` 全量测试通过；runtime 标准卡片测试覆盖新增卡片并通过；`git diff --check` 通过。

## Notes

**2026-10-25 决策与落地（Frank Qi）**

身份核对：本票 assignee 为 Frank Qi，当前分支 `feature/frank-qi`、`git config user.name=Frank Qi`，一致。

出处：2026-10-25 与用户逐条裁决。通道选 MCP 直连而非通知意图队列；令牌按研究员个人签发；卡片同时暴露发送与状态查询；审计标记并入本票修复；连通性验收以「起真实服务 + 一次真实 `send_notification`」为准。

已落地：

- 新增 `libs/mcp-libs/email-service/mcp.json`，两个工具，`failures` 含 `recipient_resolver_unavailable` 并注明为临时错误。
- `deploy-task-agent/.env.example` 增加 `EMAIL_MCP_URL`、`EMAIL_MCP_TOKEN` 及其说明。
- `email-service/src/email_service/server.py`：`get_notification_status` 的 `audited(..., write=True)` 改为 `write=False`。
- `email-service/tests/test_http.py`：新增 `test_read_status_is_logged_as_attempted_not_as_a_write`，断言读状态的账本记录只有 `attempted` 阶段。

验证：`uv run --locked --env-file .env pytest -q` → 53 passed；runtime `python -m unittest discover -s tests` → 18 passed。

MCP 连通冒烟（2026-10-25，真实 `email-service` + `mcp` 客户端，收件人用 Fake resolver）：

```text
initialize -> SciWeave Email Service
tools/list -> ['get_notification_status', 'health', 'send_notification']
send_notification isError -> False
get_notification_status isError -> False
```

`tools/list` 返回的是服务端全部三个工具，卡片只声明其中两个，说明「卡片是端侧可见子集、服务端才是完整能力面」这条约定成立。

`email-service` 测试必须带 `--env-file .env`：`EmailServiceConfig` 要求 5 个重试/轮询参数，测试未用 monkeypatch 覆盖它们，裸跑会 `missing required email-service configuration`。

已知未完成：真实 `RecipientResolver` 仍是 `UnboundRecipientResolver`，通知在落库前就以 `recipient_resolver_unavailable` 失败，所以「发出去」这条链要等 Registry 适配器落地才算真正可用；`work_agent_runtime` 仍无 MCP 客户端，卡片只被解析成目录，端侧进程尚未真正调用。

**2026-10-25 延后的文档同步（Frank Qi）**

本票只改邮件链路自身的代码与卡片。以下「通知仍走队列」的表述已过期但**本票不改**，按用户裁决「先处理邮件的票，其他先不动」：

- `ai4-te1v` 仍把 `sciweave.notification-intent` 列为四个固定 topic 之一，并写「`email-service` 只接收 `human_notification_intent`」。
- `docs/data-flow/message-queue.md` 与 `docs/data-flow/message-delivery-recovery.md` 仍把 email-service 画成该 topic 的消费者。
- `ai4-zc85`、`ai4-nfty`、`ai4-1y6q` 的验收仍写「生成 `human_notification_intent`」；这三张票已于 2026-10-25 转交 hanjiang，本票不越权改。

需要同步时，业务对象 `human_notification_intent` 的字段不变，只把承载方式从队列消息改为一次 `send_notification` 调用。

