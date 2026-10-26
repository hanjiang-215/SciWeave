# PO 通知对象取自最近一次正式版本的批准者

人工通知需要知道「这个域的项目负责人是谁」，但系统里没有 PO 名册。答案不必新建：`formal_mapping_revision.published_by` 记录的就是最近一次批准该域正式版本的人，而正式化流程在落库前已经用 `is_project_owner` 校验过这个人的资格。所以 PO 身份是派生事实，不是需要另行登记的名单。

## Status

accepted（2026-10-26）

## Considered Options

1. **在 Registry 新增「domain → PO」登记**（否决）：要新建一张表、一个新工具和一套同步机制，而它记录的是「谁被任命过」。任命与实际掌权一旦分叉，通知就会发给不再做决定的人。否决理由：为一条通知引入一个新事实源，成本和失真风险都不划算。
2. **在 TerminusDB 的 `MappingDomain` 文档里存 `project_owner_id`**（否决）：`MappingDomain` 目前只是审计用的目标类型字符串，没有实体文档。否决理由：为了让通知拿到一个收件人，先去造一个领域实体。
3. **从 `formal_mapping_revision.published_by` 派生**（采纳）：该字段 `NOT NULL`，由 `formalization.py` 写入 `approval["actor_id"]`，而放行条件是 `is_project_owner(approval["actor_id"], ...)`。它是已发生的事实，不是一份可能过期的名册。

## Consequences

- 字段名用 `latest_published_by`，**不叫** `project_owner_id`。它回答的是「最近一次批准者是谁」，不是「谁被任命为负责人」。两者通常重合，但 A 批准 r1、B 批准 r2 之后，答案是 B。
- 对外语义仍是「通知 PO」：`_dispatch_terminal_summary` 用这个字段决定收件人，代码注释链到本 ADR，免得后来者以为字段名写错了。
- `get_formal_mapping_at_revision` 需要在返回中加入 `published_by`。这是 research-map 侧的改动，不是新契约：数据早已在 `formal_mapping_revision` 表中，只是 [`_formal_query_result`](../../sci-weave/centre-control/research-map/src/research_mapping/management.py) 没有投影它。
- 将来若真的需要「PO 名册」（多人共管、轮值、审批代理），那是一次独立决策，不推翻本条：名册负责授权，本字段负责通知。
- `task_owner_id` 不走这条路。它本来就在 TaskNode 文档里，由快照适配器直接投影。
