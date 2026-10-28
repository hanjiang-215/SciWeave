---
name: owner-request-revision
description: 把候选退回给作者，并让退回这件事可执行——说清要改什么、改完谁重跑、哪些结论会因此失效。
---

# 退回一条候选

退回是三个决定里唯一「要求对方再做一次」的决定。它有两种落法，选错会让候选卡在那里：

| 情形 | 用什么 | 结果 |
| --- | --- | --- |
| 候选本身可送审，只是你没批（要改内容） | `record_review(decision="returned")` | 审核事件落盘，候选状态由你处置，作者出**新候选** |
| Wiki 候选需要新版本 | `decide_wiki_review(decision="rejected", reason=...)` | Wiki 侧没有 `returned` |

**不要用 `rejected` 来表达「先别做」或者「暂缓」。** 驳回会让作者以为这条路被判死了。
只是不想现在批，就不要动它——没有决定就是没有决定，比一个含糊的驳回有用。

## 退回时必须说清四件事

`reason` 是人唯一能拿到的东西。它要能让人不用回来问你：

1. **哪一条检查没过**。用预审报告里的检查名和 `reason_code`，不要自己重新描述一遍问题。
2. **改哪里**。指到逻辑对象（`TaskNode/logical-3`、`document_id`），不要只说「影响范围不清」。
3. **改完怎么重来**。作者要出**新候选分支**，不是在原分支上改——改原分支会让预审报告对应的
   head 消失，而报告是按 head 冻结的。
4. **哪些既有结论会失效**。如果作者在别处还有候选基于同一个基座，这次退回的改动可能让它们冲突。

## 退回之后会发生什么

- 原候选**不动**。`returned` 不修改候选内容，也不产生新版本。
- 作者的旧预审报告仍然挂在原 head 上，但它已经与新的候选无关——新候选是新 head、新报告。
- 如果作者的新候选换了一个基准版本（期间正式版本推进过），旧候选上所有基于旧基准的报告都会被
  `base_moved` 判定失效。这不是你造成的，但你要知道它会发生，别在通知里说「重新提交就行」。

## 通知作者

```
send_notification(
  notification_id="<uuid>",
  dedupe_key="revision:<proposal_id>:<candidate_head>",
  notification_kind="candidate_revision_requested",
  recipients=[{"principal_id": "<submitter_id>"}],
  subject="...",
  body="...",
  related={"proposal_id": "...", "candidate_head": "...", "buffer_id": "..."},
  schema_version="1",
)
```

- `dedupe_key` 里必须含 `candidate_head`。只用 `proposal_id` 的话，同一候选第二次退回会被当成
  重复投递返回第一次的结论，作者就收不到第二次的意见。
- `recipients` 用候选的 `submitter_id`（principal id），不要用邮箱地址——服务端通过注册表解析。
  解析不到会返回 `recipient_resolver_unavailable` 并且**什么都不写**，此时去查注册表里这个人
  有没有 `contact_email`，而不是重发。
- `body` 里写那四件事。通知是提示，不是第二份记录；真正的记录在审核事件里。

## 与「失效」的区别

失效（`head_moved` / `base_moved`）是**自动**发生的、append-only 的事实判定，由 ingest 或
Centre Agent 追加，不是你的动作。你能做的只是：看到一条候选是 `report_stale` 时，
不要批准它——它要么在重算，要么没人重算。那是去催中央侧，不是去催作者。
