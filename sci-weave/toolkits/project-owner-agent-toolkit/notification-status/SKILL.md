---
name: owner-notification-status
description: 别把「决定已落盘」当成「人已经知道」——查通知到底送到哪一步，以及为什么重发救不了它。
---

# 通知状态

审核决定在 `record_review` 返回那一刻就已经生效、已经可审计。通知是**另一条链**：
它可能没人收、可能被邮箱退、可能还在一遍遍重试。这两件事必须分开看。

## 已接受 ≠ 已送达 ≠ 已读

`send_notification` 返回的是「意图已入队」，不是「邮件发出去了」。中间还有：

```text
send_notification  →  pending          意图落盘
                     →  sending         被投递器领取
                     →  sent            每个收件人都是 sent
                     →  retryable       有人还在 pending/sending/retryable，会退避重试
                     →  permanent_failure 有收件人永久失败
                     →  invalid         内容本身不合格（不会重试）
```

`get_notification_status(notification_id)` 会给出 `delivery_status`、`attempt_count`，
以及**逐个收件人**的 `status` / `attempt_count` / `error_summary`。

逐收件人看是重点：一条通知发给三个人，两个 `sent`、一个 `permanent_failure`，
整体就是 `permanent_failure`——但那两个人已经看到了。只看总状态会让你给所有人重发一遍。

## 每种状态该怎么办

| `delivery_status` | 含义 | 重发有用吗 |
| --- | --- | --- |
| `pending` | 还没被领取 | 等；持久 `pending` 说明投递器没跑 |
| `sending` | 正在发 | 等；卡住说明投递器崩在中间，重启会恢复 |
| `sent` | 全部送达 | 什么都不用做 |
| `retryable` | 有人在退避重试 | 等；`attempt_count` 到上限会转 `permanent_failure` |
| `permanent_failure` | 有人永久失败 | **没用**。看那个人的 `error_summary` |
| `invalid` | 内容不合格 | **没用**，而且是你的错：`notification_kind`、`subject`/`body`、`schema_version`、`recipients`、`dedupe_key` 之一不符合要求 |

`permanent_failure` 的 `error_summary` 指向真正的问题：

- `recipient_unresolved` / 收件人解析失败类 ⇒ 这个人在注册表里没有可用的 `contact_email`。
  去 `get_principal_contact(principal_id)` 确认，然后 `register_principal` 补邮箱。
  重发同一条通知只会再失败一次。
- 其余发送类错误 ⇒ 邮箱侧的问题（地址被拒、SMTP 拒绝）。同样是人的信息问题，不是通知内容问题。

## 为什么不能靠重发解决

`dedupe_key` 是业务身份。用**同一个** `dedupe_key` 再发一次：

- 内容完全相同 ⇒ 返回第一次的 `notification_id` 和状态，什么都不发生；
- 内容不同 ⇒ `idempotency_conflict`，什么都不发生。

所以「重发一次试试」在这个服务上永远无效。要么修根因后换一个 `dedupe_key`（比如带上
`attempt2` 或新的时间戳），要么就接受这条通知送不到——但要让人通过别的渠道知道。

换 `dedupe_key` 前先想清楚：它之所以是幂等的，是为了防止同一个决定被通知两遍。
如果一条决定真的需要重新通知（收件人变了、内容错了），换 key 是对的；
如果只是想「再试一次」，那是在绕过幂等性，会把「发了两次」变成一个看不见的事实。

## 一条建议的顺序

1. 决定落盘（`record_review` / `decide_wiki_review`）；
2. 发通知，记下 `notification_id`；
3. 隔一会儿查 `get_notification_status`；
4. `permanent_failure` 就修收件人，别修通知；
5. 若最终确实送不到，用别的渠道告知，并把这件事写进决定之后的操作记录。

## 你不做的

- 替邮件服务重试（它自己有退避与上限）。
- 把通知状态当成决定状态。`invalid` 的通知不撤销任何一条已落盘的审核事件。
- 给 `sent` 的通知再发一遍「确认一下」。那只是多一封邮件。
