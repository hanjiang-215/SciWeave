---
name: researcher-push-task-agent-to-rework
description: 候选被退回之后，把返修真的推给本机 Task Agent，而不是自己手动改一遍候选。
---

# 推 Task Agent 返修

返修不是「再提交一次候选」。候选被退回说明**产出这份候选的那一轮执行**不够，
所以按平台约定返修必须回到产出它的那个 Task Agent 上跑，由它重跑并交一份新草稿。
你（研究员的 Personal Agent）的角色是把这条链路推起来，并且不要越界替它做。

## 先确认这是哪一类「退回」

| 你看到什么 | 实际含义 | 该做什么 |
| --- | --- | --- |
| 邮件 `candidate_revision_requested` | Project Owner 对候选按了退回 | 往下走本技能 |
| 邮件 `candidate_rejected` | 候选被驳回，不是返修 | 不要重跑；先问明白驳回理由，再决定是否重新起草 |
| 处置面里 `status=needs_revision` 的执行 | 一轮执行本身被要求返修 | 这是 Gateway 侧的动作，见 `docs/data-flow/work-agent.md` |
| 处置面里 `status=waiting` | Worker 在提问，不是返修 | 用 `answer_question` 回答，别重跑 |

两者都会以「需要再干一遍」的样子出现在你面前，但一个是治理层的裁决，一个是执行层的
处置。混起来会让一次退回变成两轮无谓的执行。

## 返修怎么真的发生

平台没有「研究员触发返修」的 MCP 工具，也不可能加一个：任务下发只走消息队列，
根任务的后续交接由正式版本发布触发。所以返修是 **Project Owner 侧**的动作——
他在裁决时指定唯一的 `repair_owner_id`，交接协调服务把返修当成一条新的
`task_handoff_ready` 投到你的 topic。Centre Workflow 不负责返修。

你能做、也必须做的三件事：

1. **保证自己可投递。** 交接协调服务只往「Agent `active` + 至少一个实例 `online`」投。
   实例状态是 `starting` 或 `offline` 时消息会留在 topic 里，看起来像「PO 没派活」。
   见 `researcher-register-instance`。
2. **确认那条交接真的来了。**
   ```
   list_pending()
   query_execution(execution_id)
   ```
   `query_execution` 返回 `draft_id`、`draft_id_source`、`error_code`、`failed_agent`。
   `draft_id_source=agent_reported` 表示草稿号是 agent 自己报的，运行时无法为那份草稿背书
   ——这种情况先核草稿，再往下一轮推。
3. **不要自己改候选。** 你手动改一遍 `change_set` 再提交，等于用一个没有执行记录支撑的
   候选覆盖掉「这一轮为什么不够」的证据。返修的证据链是：退回通知 → 新执行 → 新草稿 → 新候选。

## 返修也失败的时候

- `error_code=draft_submission_failed`：草稿写入失败，不自动重写、不自动重跑（运行时故意不重试，
  原文随 Worker 进程退出而消失）。让研究者重跑一轮，比让 Gateway 假装还能恢复它更诚实。
- `error_code` 是模型/超时类：用 `review_execution` 记一条 `rejected` 并写清原因，
  这是一条只追加的记录，不是重跑按钮。
- Worker 一直 `waiting`：`answer_question(question_id, answer)`。回答之后执行原地回到
  `queued`——注意研究员侧**不**创建 `resume_of` 新记录，这和中央侧契约不同，别按中央侧签名调用。

## 边界

`cancel_execution` 只在「这一轮明显派错了目标」时用；取消一个正在返修的执行，返修就断了。
终端执行拒绝取消并返回 `invalid_transition`。

这个套件里没有、也不该有：派发任务的工具、把草稿直接转成候选的工具、代替 PO 裁决的工具。
