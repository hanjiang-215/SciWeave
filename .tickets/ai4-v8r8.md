---
id: ai4-v8r8
status: closed
deps: []
links: []
created: 2026-10-24T14:17:45Z
type: bug
priority: 1
assignee: hanjiang
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

本票只修投递过程中的收件人进度和异常兜底，不实现真实 SMTP 发送端口，不改 MCP 工具契约的名称和参数。

## 实现决定

以下决定由 Frank Qi 在 2026-10-24 的分轮讨论中确认，是本票的实现依据。

1. **进度存储形态**：投递记录本身就是 SQLite 表 `notification_delivery`（`SCIWEAVE_EMAIL_SQLITE_PATH`），不是 JSON 文件。收件人进度用同表新增的 JSON 文本列 `recipient_progress_json` 表达，不建子表。该列保存数组，每项含 `principal_id`、`email`、`status`、`attempt_count`、`error_summary`。老记录该列为空时，按 `recipients_json` 解析出收件人并一律视为未送达，与既有行为一致，不做单独迁移脚本。
2. **未分类异常的去向**：发送端口抛出的非 `TransientSenderFailure`、非 `PermanentSenderFailure`、非 `NonRetryableContentError` 异常，一律记为 `permanent_failure`，`error_summary` 写 `sender_failure`。可重试只能由适配器显式抛 `TransientSenderFailure` 声明，服务端不猜测可恢复性。
3. **重试上限**：按收件人计数，每条通知的每个收件人最多尝试 3 次（首投 1 次加重试 2 次）。第 3 次仍失败时该收件人转 `permanent_failure`，`error_summary` 写 `max_attempts_exceeded`。上限由环境变量 `SCIWEAVE_EMAIL_MAX_ATTEMPTS` 配置，默认 3，读法与 `SCIWEAVE_EMAIL_RETRY_*` 一致。
4. **收件人级状态取值**：复用通知级状态中的 `pending`、`sending`、`sent`、`retryable`、`permanent_failure`，不使用 `invalid`。内容违规（HTML、超长、控制字符、未配置 `notification_kind`）仍在受理阶段整体拒绝，不存在单个收件人非法的情况。
5. **通知级 `attempt_count` 语义**：改为该通知各收件人 `attempt_count` 的最大值，不再表示整条通知被认领的轮数。用最大值而不是求和，避免多收件人各试一次被误读成超限。
6. **通知级状态聚合**：全部收件人为 `sent` 才是 `sent`；存在 `retryable` 或 `pending` 或 `sending` 时为 `retryable`；否则为 `permanent_failure`。不新增 `partially_sent` 状态。
7. **通知级 `error_summary`**：由通知级状态推导，`retryable` 对应 `transient_sender_failure`，`permanent_failure` 对应 `permanent_sender_failure`；收件人因超限失败时允许为 `max_attempts_exceeded`。真实原因看收件人数组，不出现「状态是可重试而摘要写永久失败」的矛盾。
8. **MCP 状态响应**：`get_notification_status` 在现有 `notification_id`、`delivery_status`、`attempt_count`、`error_summary` 之外增加 `recipients` 数组，每项含 `principal_id`、`status`、`attempt_count`、`error_summary`。不回传邮箱地址、正文、凭据和原始发送错误。`researcher`、`project_owner`、`service` 只能查自己提交的通知，`caller_type=operator` 可查任意通知的限制不变。
9. **`sending` 超时判断**：仍以通知行 `updated_at` 为准，但每次收件人进度变化都要同步刷新该字段，避免长收件人列表在发送途中被判超时后被另一个认领者重复处理。
10. **发送与记账顺序**：先发送、成功后再记录该收件人已送达。进程在这两步之间崩溃会导致极小概率重复发送。通知类消息重复比漏发更容易纠正，规格承诺的是同一 `dedupe_key` 不重复产生通知事实，不是 SMTP 层面绝对不重发。

## Acceptance criteria

- [x] 同一通知的多个收件人中，前一个已送达、后一个暂时失败时，重试只补发未送达的收件人。已送达的收件人不会收到第二封。
- [x] 逐收件人的送达进度持久化在 `notification_delivery.recipient_progress_json`，进程重启后仍按该进度续跑，不重新发送已送达的收件人。
- [x] 老记录缺少收件人进度时按 `recipients_json` 视为全部未送达，续跑行为与当前版本一致。
- [x] 发送端口抛出未分类异常时，通知离开 `sending` 并进入 `permanent_failure`，`error_summary` 为 `sender_failure`。
- [x] 单条通知因发送端口异常失败，不终止后台投递循环；同一轮里其他可投递的通知仍会被处理。
- [x] 收件人连续 3 次 `TransientSenderFailure` 后转 `permanent_failure`，`error_summary` 为 `max_attempts_exceeded`，且不再自动重试。
- [x] `SCIWEAVE_EMAIL_MAX_ATTEMPTS` 未配置时默认 3；非正整数被拒绝，与现有重试参数校验方式一致。
- [x] 通知级状态按「全部 `sent` 才 `sent`，仍有可重试则 `retryable`，否则 `permanent_failure`」聚合；通知级 `attempt_count` 是各收件人尝试次数的最大值。
- [x] `get_notification_status` 返回 `recipients` 数组，含 `principal_id`、`status`、`attempt_count`、`error_summary`，且响应不含邮箱地址、正文、凭据和原始发送错误。
- [x] 上述行为通过认证后的 MCP `send_notification` 和 `get_notification_status` 验证，使用 Fake sender，不依赖真实 SMTP。

## Blocked by

无。可以直接开工。

## Notes

**2026-10-25 实现完成（hanjiang）**

身份核对：本票 assignee 为 hanjiang，当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。

实现与验证（`sci-weave/centre-control/email-service`）：

- 收件人进度列 `notification_delivery.recipient_progress_json`：新库建表即带该列，老库由 `_ensure_retry_columns` 自动 `ALTER TABLE ADD COLUMN` 迁移；老记录该列为空时按 `recipients_json` 解析为全部未送达，与既有行为一致。
- `_deliver_one` 改为逐收件人发送：每次发送前把收件人置 `sending` 并写回进度，成功后转 `sent`，失败按异常类型转 `retryable`/`permanent_failure`；已 `sent` 或已 `permanent_failure` 的收件人跳过，重试只补发未送达的收件人。
- 未分类异常（含 `UnboundMailSender` 抛的 `EmailServiceError("sender_unavailable")`）统一记 `permanent_failure` + `error_summary="sender_failure"`；单条失败不终止投递循环，同一轮其他通知继续处理。
- 重试上限按收件人计数：`SCIWEAVE_EMAIL_MAX_ATTEMPTS`（默认 3）由 `config.py` 的 `_max_attempts()` 读取并校验非正整数；第 3 次仍失败转 `permanent_failure` + `max_attempts_exceeded`。
- 通知级状态聚合：全部 `sent` 才 `sent`，仍有 `retryable/pending/sending` 则 `retryable`，否则 `permanent_failure`；通知级 `attempt_count` 为各收件人尝试次数最大值；`error_summary` 透传收件人一致的原因（`max_attempts_exceeded`/`non_retryable_content`/`sender_failure`），否则 `permanent_sender_failure`。
- `get_notification_status` 新增 `recipients` 数组（`principal_id`/`status`/`attempt_count`/`error_summary`），不返回邮箱地址、正文、凭据和原始发送错误；既有查询权限不变。

验证：在 email-service 执行 `uv run --locked --env-file .env.example pytest -q`，58 passed；`uv run --locked --env-file .env.example python -m compileall -q src tests` 与 `git diff --check` 通过。新增测试覆盖：部分送达后重试只补发未送达收件人、未分类异常永久失败且循环继续、超限转 `max_attempts_exceeded`、非法 `SCIWEAVE_EMAIL_MAX_ATTEMPTS` 拒绝、旧库无进度列续跑。依赖无新增（复用既有 `sqlite3`/`mcp` SDK），`.env.example` 补 `SCIWEAVE_EMAIL_MAX_ATTEMPTS=3` 示例。

**2026-10-25T06:58:36Z（转交，hanjiang）**

assignee 由 Frank Qi 转交为 hanjiang。转交原因：按赛程推进安排，hanjiang 接手本票的后续推进与实现收口；原负责人 Frank Qi。转交时间 2026-10-25T06:58:36Z。

**2026-10-24T14:17:45Z**

代码审查记录（`origin/develop` 到当前工作区，含未提交改动）：

- 重复发信：`sci-weave/centre-control/email-service/src/email_service/service.py:276` 的 `_deliver_one` 用 `for recipient in recipients` 串行发送，失败后只调用 `_settle` 更新整条通知状态。
- 线程退出：同文件 `service.py:296` 只捕获三种专用异常，`ports.py:82` 的 `UnboundMailSender` 抛出的是 `EmailServiceError("sender_unavailable")`，不在捕获范围内。

两者都不改变已关闭票的验收结论，单独建票跟踪修复。归属父票 [email-service 通知意图协议与投递状态规格](ai4-f985.md)。

**2026-10-24T15:10:00Z**

设计讨论收口（Frank Qi，2026-10-24）。本票曾在讨论中倾向建 `notification_recipient_delivery` 子表，后经确认投递记录本身已是 SQLite 表、且只需按收件人保存状态与次数，改为复用同表的 JSON 列 `recipient_progress_json`，不新增表。重试上限、收件人级状态取值、通知级聚合和 MCP 返回粒度见上文「实现决定」。

规格补充已同步到 [email-service 通知意图协议与投递状态规格](ai4-f985.md) 的修订块：重试有次数上限，超限进入不可重试终态。

本票尚未开始实现，工作区没有本票对应的代码改动。
