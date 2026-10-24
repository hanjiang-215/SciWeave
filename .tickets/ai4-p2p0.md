---
id: ai4-p2p0
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
# 相同去重键的重放与冲突

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

调用方用相同 `dedupe_key` 再次提交时，邮件服务能区分「同一条通知的重放」和「拿同一个键覆盖另一条通知」。内容等价时返回既有通知，并且不发第二封。主题、正文、收件人或通知类型不一致时返回 `idempotency_conflict`，原通知保持不变。

## Acceptance criteria

- [x] 相同 `dedupe_key` 且主题、正文、收件人、通知类型等价时，返回既有 `notification_id` 和既有投递状态，Fake sender 不第二次发送。收件人等价只比较 `principal_id`。
- [x] 相同 `dedupe_key` 但主题、正文、收件人或通知类型任一不一致时，返回 `idempotency_conflict`，既有通知的内容和状态不变。
- [x] 上述行为通过认证后的 MCP 调用验证，不依赖私有表访问顺序。
- [x] 完成测试，并把验证证据回写本票。

## Blocked by

- [合法通知的受理、投递与状态查询](ai4-m1d1.md)


## Notes

**2026-10-24T07:54:13Z**

开始实现。基线为集成分支 feature/frank-qi-email 的 5d01626。实现分支 impl/ai4-p2p0。

**2026-10-24T12:20:00Z**

收口：同一 `dedupe_key` 的收件人等价只比较 `principal_id`。带凭据字样的正文按原文受理，重放返回既有通知。依赖来源、用途和许可证见 [合法通知的受理、投递与状态查询](ai4-m1d1.md)，本票未新增依赖。

在 `sci-weave/centre-control/email-service` 执行：`uv run --env-file .env pytest -q`，43 passed in 25.91s；`uv run --env-file .env python -m compileall -q src tests`，通过。分支 `feature/frank-qi`，PR https://gitee.com/qi-yueran/ai4science/pulls/35 。
