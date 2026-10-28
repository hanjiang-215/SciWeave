---
name: owner-decide-candidate
description: 对一条候选做最终裁决——批准、退回或驳回，并把批准的那条真正写进正式版本。
---

# 裁决一条候选

你是这条链上的最后一环。预审已经做过（Centre Agent），草稿一审也做过（命名空间审核人）。
你面前的东西只有两个问题：**这条候选该不该进正式版本**，以及**批准之后它是不是真的进去了**。

## 一条 Mapping 候选的完整动作序列

```
preview_candidate(proposal_id, base_formal_revision_id, candidate_head)
   ↓  preview_id（只是证据，不是凭证）
create_merge_request(preview_id)
   ↓  buffer_id
record_review(buffer_id, decision="approved"|"returned"|"rejected", reason="...")
   ↓  审核事件落盘
formalize_candidate(merge_request_id=buffer_id, operation_id="<稳定 id>")
   ↓  新的 formal_revision_id
```

四步缺一不可，而且**顺序不能跳**：

- `preview_candidate` 只产出证据。它返回的 `preview_id` 没有任何 buffer 工具接受。
  以前 Mapping 侧到这一步就没有下一个工具了，Project Owner 拿到一个 preview 却没有地方送决定；
  `create_merge_request` 就是补上的那一步。
- `record_review` 的 `buffer_id` 必须来自 `create_merge_request`。
- `formalize_candidate` 的参数名是 `merge_request_id`，值就是那个 `buffer_id`——
  `formalization.py` 用 `mapping_merge_request_buffer.buffer_id` 去 join。

## 三个决定

| decision | 含义 | 之后 |
| --- | --- | --- |
| `approved` | 同意进正式版本 | 必须再调 `formalize_candidate`，否则什么都没发生 |
| `returned` | 退回，要作者出新版本 | 原候选不动；通知作者 |
| `rejected` | 驳回 | 原候选不动；通知作者 |

**批准不等于正式化。** 这是最容易出错的一步：`record_review(approved)` 只写了一条审核事件，
正式图一个字节都没改。`formalize_candidate` 才会。中间任何失败（MCP 断、进程被杀）都停在
「已批准但未正式化」，而河对岸的人以为已经发布了。

同样，`formalize_candidate` 会**重新核对**批准者是不是这个域的 Project Owner
（`owner_approval_required`）。你既然在这里，这条通常不是问题；但如果你在用别人的令牌跑，
它会拒绝——那不是故障，是设计。

## 正式化失败怎么办

`formalize_candidate` 返回 `reconciliation_required` 时**不要换一个 `operation_id` 重试**。
换 id 等于声明「这是另一次正式化」，而第二次正式化在同一个 buffer 上是不允许的，
`operation_identity_mismatch` 会拦住你。

正确做法是 `reconcile_formalization(operation_id="<原来那个>")`：它用同一个操作身份去
核对 SQLite 激活、正式指针和 TerminusDB 快照三者是否一致，然后给出 `succeeded` 或
继续报 `reconciliation_required` 并带原因码。

其他形式的失败（`merge_request_unavailable`、`stale_base`、`candidate_mismatch`）都不是重试能解决的：

- `stale_base`：候选基准已不是当前正式版本。这不是 bug，是有人在这期间推进了正式版本。
  候选要重做，`reconcile` 不会帮你绕过它。
- `candidate_mismatch`：buffer 里的 head、base 或 proposal 状态与现在不符。先查发生了什么，
  不要硬推。

## Wiki 侧的差异

```
preview_wiki_review(proposal_id)                 → preview_id（仅供参考）
create_wiki_merge_request(proposal_id, merge_request_id)   ← id 由你给
decide_wiki_review(merge_request_id, decision="approved"|"rejected", reason, selected_solution_id)
formalize_wiki(merge_request_id, operation_id)
```

三处不同，每一处都会绊人：

1. `create_wiki_merge_request` 的 `merge_request_id` 是**你传进去的**，不像 Mapping 那样由服务端
   从 `preview_id` 派生。所以挑一个稳定值（`wiki-mr-<proposal_id>`）并在重试时复用它。
   换新 id = 第二条 merge request。
2. `decide_wiki_review` 必填 `selected_solution_id`。一条 Wiki 候选可能带多个方案，决定要指明批的是哪个。
3. Wiki 的决定只有 `approved` / `rejected`，**没有 `returned`**。要让作者出新版本，就用
   `rejected` + 写清理由，理由就是作者唯一的依据。

## 通知

决定落盘后通知作者，用 `candidate_revision_requested`（退回）或 `candidate_rejected`（驳回）。
批准不需要发这一类——正式化成功后由领域事件驱动后续，再给作者发一封「你通过了」会让人以为
还要做什么。

## 你不能做的

- 预审候选、追加预审日志、生成混合候选。你能读候选，但读的是点名的那些；
  `list_reviewable_candidates` 那张全量快照不在你的卡片里，`centre` 能力也不在你的上限里。
- 一审草稿。草稿是命名空间审核人的事。
- 改候选内容。`returned` 和 `rejected` 都不动原分支。
