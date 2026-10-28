---
type: concept
created: 2026-10-28
updated: 2026-10-28
sources: [repository-facts]
tags: [workflow, execution, handoff, governance]
---

# 核心业务流程

SciWeave 的主闭环是：正式路线 → 依赖重算 → 可执行交接 → 一轮 Agent 执行 → 草稿 → 人审与候选 → 中央预审 → Owner 正式化 → 新正式版本。

```text
PO 正式发布 Mapping
  -> formal_revision_published
  -> Coordinator 读取精确正式快照
  -> PendingHandoff / task_handoff_ready
  -> Task Agent subscriber
  -> ExecutionRecord + Worker Lease
  -> 短生命周期 Worker / fast-agent loop
  -> Draft Buffer draft_id
  -> 人审草稿
  -> accepted 草稿由人调用领域 MCP 创建 candidate
  -> 机械校验
  -> Centre Agent 预审报告 / merged candidate
  -> PO 影响预览与审核
  -> formalize，激活精确正式 Commit
  -> 发布治理事件并重新计算下游
```

## 1. 正式版本与交接

Research Mapping 正式版本发布或任务完成后，事件进入 `sciweave.governance-events`。Coordinator 查询正式 Mapping、Registry 和自身的等待状态，检查目标节点、正式依赖、所需输出、激活条件和正式执行主体。

只有条件全部满足时才发布 `task_handoff_ready`，消息进入 `sciweave.task-handoff.<agent_id>`。条件不满足时，Coordinator 创建/更新 `PendingHandoff`，必要时通过 email-service MCP 通知负责人。

Coordinator 不修改 Mapping、不授予权限、不创建 ExecutionRecord，也不直接启动 Worker。根节点需要 Project Owner 显式派发。

## 2. Task Agent 执行

Task Agent subscriber 收到 `task_handoff_ready` 后：

1. 按 `task_node_id` 找到稳定 `session_id`。
2. 在 SQLite 事务中创建 `queued` 的 ExecutionRecord 并记录审计。
3. 原子领取本地 Worker Lease，成功后启动一次 Worker。
4. Worker 执行 fast-agent-mcp 工作流，完成后由 Agent 调用 Draft Buffer 的 `create_draft`。
5. 保存 `draft_id`，将 ExecutionRecord 置为 `completed`，再提交消息 offset。

ExecutionRecord 状态包括 `queued`、`running`、`waiting`、`completed`、`needs_revision`、`rejected`、`human_takeover`、`failed` 和 `cancelled`。Gateway 不保存草稿的接纳状态。

## 3. 草稿与候选

Draft Buffer 状态为：

```text
drafting -> submitted -> accepted -> promoted
                     \-> rejected -> 重新 submitted
```

`submitted` 时固定 `submitted_commit`，审核对象是这个 Commit 而不是最新内容。`accepted` 不会自动创建候选；人必须用领域管理 MCP 将固定草稿推进候选。候选创建后由 `mark_promoted` 记录推进关系。

## 4. 预审与正式化

领域服务对候选执行机械校验。Centre Agent 读取候选和正式基准，追加不可变预审报告；必要时创建记录全部来源的混合候选。Project Owner 查看预审材料、影响范围和冲突，批准、退回或拒绝候选。只有 Owner 正式化后，候选才成为正式版本并发布治理事件。

## 5. 下游传播

Coordinator 只根据正式快照计算依赖。Registry 中存在 Agent 只说明它被登记，不能替代正式 `executor_refs`。正式输出满足阻塞边后，Coordinator 才能为下游产生新的 `task_handoff_ready`。

## 相关页面

- [[concepts/research-mapping-and-wiki]]
- [[concepts/work-agents-and-governance]]
- [[concepts/deployment-and-operations]]
