---
id: ai4-v8r8
status: open
deps: []
links: []
created: 2026-10-24T14:17:45Z
type: bug
priority: 1
assignee: Frank Qi
parent: ai4-f985
tags: [centre-control, email-service, notification, delivery]
---
# 邮件投递：逐收件人进度与发送端口异常兜底

## Parent

[email-service 通知意图协议与投递状态规格](ai4-f985.md)

## What to build

代码审查在 `origin/develop` 到 `feature/frank-qi` 的邮件实现里发现两个投递缺口，都在 `sci-weave/centre-control/email-service/src/email_service/service.py` 的 `_deliver_one`。

1. 一条通知的多个收件人是串行发送的，但投递库只记录整条通知的状态，没有记录每个收件人是否已送达。第一个收件人发送成功、第二个收件人暂时失败时，通知进入 `retryable`；下次重试从第一个收件人重新开始，已成功的收件人会收到第二封。

2. `_deliver_one` 只捕获 `TransientSenderFailure`、`PermanentSenderFailure`、`NonRetryableContentError` 三种异常。发送端口抛出其他异常时，后台投递线程直接退出，记录停留在 `sending`，在进程重启前既不重试，也不再处理其他通知。进程入口注入的 `UnboundMailSender` 抛出的 `EmailServiceError("sender_unavailable")` 就是这种情况。

本票只修投递过程中的收件人进度和异常兜底，不实现真实 SMTP 发送端口，不改 MCP 工具契约。

## Acceptance criteria

- [ ] 同一通知的多个收件人中，前一个已送达、后一个暂时失败时，重试只补发未送达的收件人。已送达的收件人不会收到第二封。
- [ ] 逐收件人的送达进度持久化在投递库，进程重启后仍按该进度续跑，不重新发送已送达的收件人。
- [ ] 发送端口抛出未分类异常时，通知离开 `sending`，进入 `retryable` 或 `permanent_failure`，并写入稳定的 `error_summary`。
- [ ] 单条通知因发送端口异常失败，不终止后台投递循环；同一轮里其他可投递的通知仍会被处理。
- [ ] 上述行为通过认证后的 MCP `send_notification` 和 `get_notification_status` 验证，使用 Fake sender，不依赖真实 SMTP。
- [ ] `get_notification_status` 的响应仍然不含正文、凭据和原始发送错误。

## Blocked by

无。可以直接开工。

## Notes

**2026-10-24T14:17:45Z**

代码审查记录（`origin/develop` 到当前工作区，含未提交改动）：

- 重复发信：`sci-weave/centre-control/email-service/src/email_service/service.py:276` 的 `_deliver_one` 用 `for recipient in recipients` 串行发送，失败后只调用 `_settle` 更新整条通知状态。
- 线程退出：同文件 `service.py:296` 只捕获三种专用异常，`ports.py:82` 的 `UnboundMailSender` 抛出的是 `EmailServiceError("sender_unavailable")`，不在捕获范围内。

两者都不改变已关闭票的验收结论，单独建票跟踪修复。归属父票 [email-service 通知意图协议与投递状态规格](ai4-f985.md)。
