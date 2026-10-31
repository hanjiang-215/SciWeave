---
name: owner-finish-task
description: 派发的任务跑完后，负责人核对结果并把该任务在看板上标记为已完成（含驳回与退回）。
---

# 任务跑完了，负责人怎么确认完成

派发（`dispatch_root_task`）只是把任务交给执行者，**不代表做完**。执行跑完后，
必须由负责人确认，任务才会在看板上变成「已完成」，下游节点也才会被放行。

## 先看有什么在等确认

```
list_pending(task_node_id="R")      # 或 list_pending() 看全部
query_execution(execution_id="...")
```

判断能不能确认：

- `status` 不是 `completed`（还是 `queued` / `running`）→ 还没跑完，别确认；
- `status == completed` 且 `draft_id` 有值 → 成果已经写进草稿箱，可以核对后确认；
- `pending_question` 有值 → 它在等一个回答，先 `answer_question`。

## 确认完成（关键动作）

```
confirm_execution(
  execution_id="...",
  decision="accepted",
  reason="负责人复核：交付物齐全，路线冻结口径可执行",
  idempotency_key="confirm:<execution_id>:accepted",
)
```

- `accepted` = 认可这次执行 → 看板变「已完成」，协调服务把下游节点从 `waiting` 放行；
- `rejected` = 不认可 → 打回，需要说明原因；
- 只想让它按意见重做 → 用 `review_execution(decision="request_revision", ...)`，
  让研究员那边推返修（`push-task-agent-to-rework`），而不是自己动手改。

**幂等**：重试必须沿用同一个 `idempotency_key`，不要改 `execution_id`。
服务端对同一个 key 是幂等的；换个 key 就是第二次确认。

## 容易搞错的地方

1. **确认完成 ≠ 成果入库。** 确认只让看板标「已完成」；成果进正式地图仍要走
   草稿 → 候选 → `create_merge_request` → `record_review(approved)` → `formalize_candidate`。
2. **预审完成不算完成。** 预审（centre-prereview / 占位摘要）的完成会被看板忽略，
   只有真实执行且被确认的完成才计入。
3. **不要替负责人「觉得应该完成了」就确认。** 没有负责人的明确表态，不要 accepted。
4. **不要确认别人的任务。** 确认只针对本轮派发、自己负责的节点。
5. **派发成功不等于完成。** `dispatch_root_task` 返回 accepted 只说明任务入了队。

## 确认之后

- `list_pending` 里该执行不再是待确认状态；
- 看板上该节点显示已完成，下游节点从待处理变为可执行；
- 若还想让成果进正式图，交给 `decide-candidate` 那条链路。
