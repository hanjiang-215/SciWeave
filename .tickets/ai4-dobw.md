---
id: ai4-dobw
status: closed
deps: []
links: []
created: 2026-10-24T12:15:57Z
type: feature
priority: 2
assignee: Frank Qi
parent: ai4-f985
tags: [centre-control, email-service, notification]
---
# 补齐邮件健康分项、运维查询与调用方约束

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

首版四张实现票没有覆盖这些规格缺口。本票补齐公开健康探针对邮箱未配置的表达、认证健康的 `degraded`、运维身份查询、字符集校验、扩展 `notification_kind` 的调用方限制，以及状态查询里的安全错误摘要。

投递服务不扫描正文里的凭据。不把凭据写进通知是撰写方的责任，留给后续 Work Agent 等调用方，不在本票。

## Acceptance criteria

- [x] 未认证 `GET /health` 在公共邮箱未配置时返回 `not_configured`，且只含 `status`、服务名和 API 版本。
- [x] 认证 MCP `health` 在访问账本不可用但投递库可用时，整体状态为 `degraded`。
- [x] 运维身份按授权范围查询投递状态；普通调用方仍只能查询自己提交的通知。
- [x] 主题和正文不符合服务端字符集时记为 `invalid`，不发信。
- [x] 扩展 `notification_kind` 只对配置允许的调用方受理；未配置类型仍然拒绝。
- [x] `get_notification_status` 在失败时返回不含正文、凭据或原始发送错误的 `error_summary`。
- [x] 上述行为通过认证后的 MCP 或未认证健康探针验证，不使用真实 SMTP，也不消费 Redpanda。

## Blocked by

无。可以开工。不实现真实发信、真实 Registry 适配，也不编写撰写通知的提示词。

## Notes

**2026-10-24T12:20:00Z**

从 [合法通知的受理、投递与状态查询](ai4-m1d1.md)、[相同去重键的重放与冲突](ai4-p2p0.md)、[非法输入与不可重试失败](ai4-54n6.md)、[暂时失败、自动重试与重启恢复](ai4-zjge.md) 的收口中拆出。这四张票按各自验收关闭，不回头实现本票。

**2026-10-24T12:40:30Z**

实现决定（Frank Qi 确认，2026-10-24）：

1. 字符集只拒绝控制字符。主题和正文按 JSON 进来已经是 Unicode。服务拒绝 NUL 和其他 Unicode 类别 Cc 的控制字符，保留换行、回车和制表符。不做 GBK 或 UTF-8 编码检测。不合规则记为 invalid，不发信。
2. 运维身份使用现有 SCIWEAVE_EMAIL_TOKENS_JSON 的 caller_type=operator。它可以按 notification_id 查询任何人提交的投递状态，仍然看不到正文、凭据和原始发送错误。researcher、project_owner、service 仍只能查自己提交的。
3. 13 个核心 notification_kind 对所有已认证调用方开放。额外类型放在环境变量 SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON，按 caller_id 列出。没配这个变量时只有那 13 个。未列入的类型仍是 invalid，不发信。

**2026-10-24T12:51:49Z**

验证：在 sci-weave/centre-control/email-service 执行 uv run --env-file .env pytest -q，52 passed in 28.35s；uv run --env-file .env python -m compileall -q src tests 通过。没有真实 SMTP，也没有消费 Redpanda。

未认证 GET /health 在公共邮箱环境变量缺失时返回 503，正文只有 status=not_configured、service 和 api_version。认证 health 在删掉 audit_call 后整体为 degraded，投递库仍是 ready。caller_type=operator 能按 notification_id 读到他人的 sent 状态，其他 service 仍是 denied，响应不含正文和凭据。NUL、ESC、DEL 记为 invalid 且不发信；换行、回车、制表符和中文仍投递。SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON 只放行列出的 caller_id，marketing_blast 仍拒绝。永久发送失败的 error_summary 是 permanent_sender_failure，不包含正文、邮箱口令或原始 550 文本。
