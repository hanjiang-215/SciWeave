---
id: ai4-m1d1
status: open
deps: [ai4-f985, ai4-ujvn]
links: []
created: 2026-10-23T13:56:20Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-p5f3
tags: [implementation, centre-control, email-service, notification, message-queue, ready-for-agent]
---
# 实现 email-service 通知意图 MCP 与投递状态

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

建立独立的 `email-service` Python 子项目。受鉴权的服务调用方通过 MCP `send_notification` 提交 `human_notification_intent`；服务校验通知封套、解析收件人、使用统一公共邮箱发送纯文本邮件、持久化投递状态，并对重复请求、暂时失败和永久失败提供可观察且可恢复的结果。

首版只使用 MCP 作为输入入口，不消费 Redpanda 通知 topic；真实 SMTP 或第三方邮件服务通过可替换发送端口接入，测试使用 Fake sender。邮件投递失败不能修改或回滚 Research Mapping、LLM-Wiki、候选、正式版本、PendingHandoff 或 Task Agent ExecutionRecord。

## Implementation Contract

- 实现 `send_notification` MCP 工具，返回 `notification_id`、投递状态、重复标记或稳定错误码。
- 校验 `schema_version`、`notification_kind`、`recipients`、`subject`、纯文本 `body`、`related` 和 `dedupe_key`。
- 优先通过 `principal_id` 解析收件地址；联系人缺失或调用方地址与登记不一致时拒绝发送。
- 发件人、SMTP 地址和凭据仅从 email-service 自己的环境配置读取；调用方不能覆盖。
- 持久化 `pending`、`sending`、`sent`、`retryable`、`permanent_failure`、`invalid` 状态。
- 相同 `dedupe_key` 的等价请求不重复发送；内容冲突返回 `idempotency_conflict`。
- 进程重启后恢复未完成和可重试投递；永久失败保留可查询记录。
- 对外接口记录调用者、通知类型、关联对象、结果和错误码，不记录凭据和不必要的敏感正文。

## Acceptance criteria

- [ ] MCP `send_notification` 可通过认证调用，并返回稳定结果。
- [ ] 完成通知封套、收件人解析、主题/正文限制和 `notification_kind` 校验。
- [ ] 公共邮箱发件配置不暴露给调用方，首版不消费 Redpanda notification topic。
- [ ] 投递状态和幂等键持久化，重复请求不重复发送，冲突请求被拒绝。
- [ ] 暂时失败可重试，永久失败和非法输入可观察且不无限重试。
- [ ] 重启恢复 `pending`、超时 `sending` 和 `retryable` 记录。
- [ ] 邮件失败不改变任何领域事实或任务调度状态。
- [ ] 使用临时 SQLite、Fake sender 和 MCP 行为测试验证成功、重复、冲突、失败、恢复和鉴权拒绝。
- [ ] 完成 `uv sync`、测试、`compileall`、README、`.env.example` 和验证证据回写。

## Blocked by

- [email-service 通知意图协议与投递状态规格](ai4-f985.md)

## Notes

**2026-10-23T15:52:39Z**

真实 RecipientResolver 适配依赖注册表通知联系人契约；本票保留 Fake Resolver 的核心实现，但在 ai4-ujvn 收敛前不接入真实 Registry。
