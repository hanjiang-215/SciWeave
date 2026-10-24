---
id: ai4-zjge
status: closed
deps: [ai4-m1d1]
links: []
created: 2026-10-24T05:26:07Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-f985
tags: [implementation, centre-control, email-service, notification, ready-for-agent]
---
# 暂时失败、自动重试与重启恢复

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

Fake sender 暂时失败时，通知进入 `retryable`，后台按退避自动重试，成功后变为 `sent`。进程重启后继续处理 `pending`、超时的 `sending` 和 `retryable`，并沿用原来的 `dedupe_key`，不生成新的通知事实。没有给调用方的重试工具。已经永久失败的记录仍可查询，且不会被自动重试。

## Acceptance criteria

- [x] 发送暂时失败时，通知进入 `retryable`；后台退避重试成功后，状态变为 `sent`，且不产生第二封独立通知。
- [x] 进程重启后继续处理 `pending`、超时的 `sending` 和 `retryable`，复用原 `dedupe_key`。
- [x] 不提供调用方 `retry_notification`。人工再次发送必须使用新的 `notification_id`。
- [x] `permanent_failure` 与 `invalid` 在重启后仍可查询，且不会被自动重试。
- [x] 使用临时 SQLite 和 Fake sender 验证暂时失败、重试成功和重启恢复。
- [x] 完成测试，并把验证证据回写本票。

## Blocked by

- [合法通知的受理、投递与状态查询](ai4-m1d1.md)


## Notes

**2026-10-24T07:54:13Z**

开始实现。基线为集成分支 feature/frank-qi-email 的 5d01626。实现分支 impl/ai4-zjge。

**2026-10-24T12:20:00Z**

收口验证：暂时失败进入 `retryable` 后可送到 `sent`；重启后续跑 `pending`、超时 `sending` 和 `retryable`；没有调用方 `retry_notification`；`permanent_failure` 与 `invalid` 不会被自动重试。依赖来源、用途和许可证见 [合法通知的受理、投递与状态查询](ai4-m1d1.md)，本票未新增依赖。

在 `sci-weave/centre-control/email-service` 执行：`uv run --env-file .env pytest -q`，43 passed in 25.91s；`uv run --env-file .env python -m compileall -q src tests`，通过。分支 `feature/frank-qi`，PR https://gitee.com/qi-yueran/ai4science/pulls/35 。
