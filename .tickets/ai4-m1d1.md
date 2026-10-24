---
id: ai4-m1d1
status: closed
deps: [ai4-f985, ai4-ujvn]
links: []
created: 2026-10-23T13:56:20Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-f985
tags: [implementation, centre-control, email-service, notification, ready-for-agent]
---
# 合法通知的受理、投递与状态查询

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

认证调用方提交一条合法的 `human_notification_intent` 后，邮件服务用 Fake `RecipientResolver` 解析收件人，持久化并返回 `accepted_for_delivery`，再由 Fake sender 投递成功。调用方之后只能查到自己这条通知的投递状态，看不到正文、凭据或原始发送错误。未认证的 HTTP `/health` 和认证后的 MCP `health` 可用。访问账本和投递记录分开。邮件成败不改变任何领域事实。

本票不实现重复提交、非法输入、暂时失败重试或进程重启恢复。那些行为由后续实现票承接，并且都只等本票。

## Acceptance criteria

- [x] 独立的 email-service 可通过官方 Python `mcp` SDK 的 Streamable HTTP 启动；HTTP `GET /health` 无需认证，且只返回最小状态。
- [x] 认证调用 `send_notification` 提交合法封套后，Fake `RecipientResolver` 按 `principal_id` 解析收件人，持久化成功时返回 `accepted_for_delivery`。
- [x] Fake sender 将这条通知送到 `sent`；调用方用 `get_notification_status` 只能看到自己提交的投递状态，响应不含正文、凭据或原始发送错误。
- [x] 认证 MCP `health` 返回分项状态。MCP 访问经共享调用账本留痕，投递事实只写 delivery store，两者只通过 `notification_id` 弱关联。
- [x] 发件人、SMTP 地址和凭据只来自本服务环境配置；调用方不能覆盖。测试不使用真实 SMTP，也不消费 Redpanda。
- [x] 邮件成败不修改 Research Mapping、LLM-Wiki、候选、正式版本、PendingHandoff 或 Task Agent ExecutionRecord，也不发布任务交接。
- [x] 使用临时 SQLite、Fake Resolver、Fake sender 和认证 MCP 行为测试验证成功路径与未认证拒绝。
- [x] 完成安装、测试、编译检查、说明、环境变量示例，并把验证证据回写本票。

## Blocked by

无。规格票和 Registry 登记规格都已关闭，本票可以开工。真实 Registry 适配和真实 SMTP 不在本票。

## Notes

**2026-10-23T15:52:39Z**

真实 RecipientResolver 适配依赖注册表通知联系人契约；本票保留 Fake Resolver 的核心实现，但在 ai4-ujvn 收敛前不接入真实 Registry。

**2026-10-24T05:20:00Z**

阻塞已解除。`ai4-f985` 与 `ai4-ujvn` 均已关闭，`deps` 保留为已满足的前置，不再挡住开工。本票按完整规格实现，使用 Fake `RecipientResolver` 和 Fake sender。真实 Registry 适配留到 Registry 实现完成之后，不拆进本票，也不作为本票的新依赖。

**2026-10-24T05:26:00Z**

本票收成纵向切片「合法通知的受理、投递与状态查询」，不再覆盖整份规格。幂等冲突见 [相同去重键的重放与冲突](ai4-p2p0.md)，非法输入见 [非法输入与不可重试失败](ai4-54n6.md)，重试与重启恢复见 [暂时失败、自动重试与重启恢复](ai4-zjge.md)。这三张票都只依赖本票。上一则「按完整规格实现」的范围说明因此作废，原文保留。

**2026-10-24T06:43:10Z**

2026-10-24：开始实现。集成分支 feature/frank-qi-email，本票实现分支 impl/ai4-m1d1。范围仅限合法通知受理、Fake 投递与状态查询。

**2026-10-24T12:20:00Z**

收口验证在 `feature/frank-qi` 工作区完成，对应 PR https://gitee.com/qi-yueran/ai4science/pulls/35 。规格里尚未实现的健康分项、运维查询、字符集、扩展类型和安全错误摘要见 [补齐邮件健康分项、运维查询与调用方约束](ai4-dobw.md)，不在本票。

依赖（`sci-weave/centre-control/email-service` 的 `pyproject.toml` 与 `uv.lock`）：

| 依赖 | 锁定版本 | 来源 | 用途 | 许可证 |
| --- | --- | --- | --- | --- |
| mcp | 1.30.0 | PyPI | 官方 MCP Streamable HTTP | MIT |
| starlette | 1.9.0 | PyPI | 未认证 `GET /health` | BSD-3-Clause |
| pydantic | 2.14.1 | PyPI | `server.py` 直接引用 `ValidationError` | MIT |
| httpx | 0.28.1 | PyPI，开发依赖 | 测试里的 MCP 客户端 | BSD-3-Clause |
| pytest | 8.4.2 | PyPI，开发依赖 | 测试 | MIT |
| uvicorn | 0.54.0 | PyPI，开发依赖 | 测试里启动临时服务 | BSD-3-Clause |
| sciweave-audit-trail | 0.2.0 | 仓库 path `../shared/audit-trail` | MCP 访问账本 | 未单独声明许可证，仅本仓库使用 |

在 `sci-weave/centre-control/email-service` 执行：`uv sync`；`uv run --env-file .env pytest -q`，43 passed in 25.91s；`uv run --env-file .env python -m compileall -q src tests`，通过。服务不写入 Research Mapping、LLM-Wiki、候选、正式版本、PendingHandoff 或 ExecutionRecord。

**2026-10-24T14:20:01Z**

2026-10-24T14:22:00Z 真实 SMTP 联调补记：按 .env.example 复制出的 .env 无法启动服务。uv --env-file 会把未加引号的 JSON 值剥掉双引号，SCIWEAVE_EMAIL_TOKENS_JSON 解析失败并报 must be a JSON object。已在 .env.example 用单引号整体包裹 JSON 值，并在 README 配置章节写明。另外用一次性脚本经真实 MCP send_notification 调用、真实 163 SMTP 投递成功，状态为 sent，未改产品代码。
