---
id: ai4-2raq
status: open
deps: []
links: [ai4-2982, ai4-edrp]
created: 2026-10-26T07:36:24Z
type: feature
priority: 1
assignee: hanjiang
parent: ai4-xup8
tags: [implementation, research-map, mcp]
---
# get_formal_mapping_at_revision 返回 published_by

## Background

`task_terminal_summary` 需要知道「这个域的项目负责人是谁」才能决定收件人。系统里没有 PO 名册，答案在 `formal_mapping_revision.published_by`：该字段 `NOT NULL`，由 `formalization.py` 写入 `approval["actor_id"]`，而放行条件已经过 `is_project_owner(approval["actor_id"], ...)` 校验。它是已发生的事实，不是一份可能过期的名单。依据见 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)。

数据早就在表里，只是没有对外暴露。[`_formal_query_result`](../sci-weave/centre-control/research-map/src/research_mapping/management.py) 组装返回时投影了 `store_id`、`branch_id`、`commit_hash`、`content_digest` 和 `documents`，唯独漏了 `published_by`。

## Scope

在 `get_formal_mapping_at_revision` 的成功返回中加入 `published_by`，取值为 `formal_mapping_revision.published_by`。

这**不是新契约**：`ai4-2982` 定的传输方式、一致性闸门、鉴权和审计边界全部不变，只是多返回一个已在同一张表里的列。同时确认 `get_formal_mapping` 是否也需要同样字段——两者共用 `_formal_query_result`，改一处即同时生效，需在测试里覆盖两个入口。

失败路径（`no_such_revision` / `revision_not_found` / 一致性闸门拒绝）的返回结构保持不变，此时没有 `published_by` 可给。

## Acceptance Criteria

- [ ] `get_formal_mapping_at_revision` 成功返回中包含 `published_by`，值等于该 revision 在 `formal_mapping_revision` 表中的记录。
- [ ] `get_formal_mapping` 成功返回中同样包含 `published_by`，两个入口一致。
- [ ] 失败返回不包含 `published_by`，结构与改动前相同。
- [ ] 测试覆盖：正常读取、未知版本、两个入口字段一致。
- [ ] 既有 115 项测试全部仍通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 字段名保持 `published_by`，不改成 `project_owner_id`。它回答「最近一次批准者是谁」，不是「谁被任命为负责人」；两者通常重合，但 A 批准 r1、B 批准 r2 之后答案是 B。下游会把它映射为 `FormalSnapshot.latest_published_by`（`ai4-edrp`），对外仍承担「通知 PO」的语义。
- 本票不动 `is_project_owner` 的能力判定逻辑，也不新增 PO 登记表。将来若真的需要多人共管、轮值或审批代理，那是一次独立决策。
- 改动会牵动 `research-map` 的 MCP 接口测试，属于 hanjiang 实现的模块；本票由 Frank Qi 承接是因为它服务于 `ai4-edrp` 的收件人链路，合并前需与模块实现方确认无契约冲突。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。
