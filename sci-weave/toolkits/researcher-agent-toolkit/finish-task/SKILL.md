---
name: researcher-finish-task
description: 任务跑完后，研究员用大白话说"搞定/确认完成"，把该任务在看板标记为已完成。
---

# 任务做完了，怎么让它显示"已完成"

看板上的任务，只有**研究员明确确认**之后才会变成「已完成」。以前 worker 一跑完就自动变绿，
现在不是了：worker 跑完只是「待确认」，你（Agent）要帮研究员确认一下，它才算真正完成。

## 研究员会怎么说

"这个任务 OK 了""结果没问题，确认完成""帮我把它标记完成""这条我可以收工了""成了，收尾吧"。

听到这类话，先核对，再帮 TA 确认。**不要**在研究员没表态时自己替 TA 确认。

## 确认之前先核对

1. `list_pending`：看有没有"跑完了、等你确认"的执行。
2. 对那一条 `query_execution(execution_id)`：
   - `status` 不是 `completed`（还在 `queued`/`running`）→ 告诉研究员"还没跑完，再等等"。
   - `draft_id` 有值 → 结果已经写进草稿箱了，可以放心确认。
3. 确认研究员**真的认可结果**（不是随口一说）再提交。

## 确认完成（关键动作）

    review_execution(execution_id="...", decision="accepted", reason="研究员确认结果无误")

- `accepted` = 认可这次执行结果 → 该任务在**看板变成「已完成」**，下游任务才可以继续。
- `rejected` = 不认可 → 任务退回（再走 `push-task-agent-to-rework`）。

如果套件配置了 `CONFIRM_UPLINK_URL`，这个确认会同步到中央服务器；如果返回
`centre_confirmation_failed`，说明本地记了但没同步上——**用同样的理由重试一次**
（服务器侧是幂等的），别改 `execution_id`。

## 要说清楚的重要区别（研究员容易误解）

- **「确认完成」= 这次执行结果被认可、看板标已完成。它不会把成果自动写进正式科研地图。**
- 如果还想让成果**进入正式地图/知识库**，那是另一件事，用 `promote-draft` 把草稿提成候选
  （还需要 Project Owner 审核）。

## 别做的事

- 不要替研究员"觉得应该完成了"就擅自 `accepted`。
- 不要在任务还没跑完（`queued`/`running`）时确认——会报 `invalid_transition`。
- 不要用 `review_execution` 去动别人任务的执行。
- 不要把"确认完成"说成"成果已入库"——那是两回事。
