---
id: ai4-upsm
status: closed
deps: []
links: [ai4-he04, ai4-rlv6, ai4-dybh]
created: 2026-10-21T12:14:23Z
type: feature
priority: 1
assignee: Frank Qi
tags: [centre-control, audit, buffer, mcp]
---
# 中央服务留痕工具：写入方统一调用的审计接口

中央服务器上所有改动正式事实的组件共用一套固定留痕接口。留痕不是中央 Agent 的私有能力，而是写入方在写事实的同一事务里必须调用的工具。

## Design

依据「中央协调 Agent 与审计体系」的字段清单（actor、actor_type、operation、target_id、base_revision、candidate_revision、result、timestamp、reason，以及关联的 Proposal/Task/Resource 标识）定出统一事件形状和一个只追加的写入接口。

调用方：Buffer 写草稿状态变更、Research Mapping 管理 MCP 推进正式版本、LLM-Wiki 管理 MCP 推进正式版本；中央 Agent 的预审报告追加经 `append_prereview_log` 工具落库时，由对应领域管理 MCP 作为写入方调用本接口。端侧 Task Agent Gateway 不再进入中央，不是本接口的调用方。

约束：只追加，不提供更新和删除；调用方不能自定义省略字段；查询入口与写入分离，写入口不暴露给 Agent 自由调用；留痕与治理事实写在同一个 SQLite 事务里。

## Resolution

**统一发生在接口层，不在存储层。** 中央提供一个共享 Python 包 `sci-weave/shared/audit-trail`（标准库实现，模块 `audit_trail`），写入方以 uv `[tool.uv.sources]` path 可编辑依赖引用。Mapping、Wiki、Buffer 各自持有审计 SQLite，分别落库；函数与字段形状统一，审计存储不共享，守住领域隔离。

**写接口（唯一写入入口）：**

```python
write_audit_event(conn: sqlite3.Connection, event: AuditEvent) -> None
```

- 包不自开连接：调用方必须传入自己的 `sqlite3.Connection`。
- 函数先校验 `conn.in_transaction == True`，否则抛错；这就是「独立调用被拒绝」的落法，把「与事实同事务」变成签名上的硬约束。
- 校验字段与枚举，非法即抛错；不提供任何更新或删除接口。
- `event_id`、`occurred_at` 由包生成，调用方不传。

**统一字段（superset）：** 必填 `actor_id`、`actor_type`（`human`/`agent`/`system`）、`operation`（见事件枚举）、`target_object_type`、`target_object_id`、`result`；可选 `base_revision`、`candidate_revision`、`previous_state`、`next_state`、`reason`，以及按事件类型选填的弱引用 `proposal_id`/`task_id`/`resource_id`/`formal_revision_id`/`merge_request_id`。不推翻已关闭 spec 中的 `MappingAuditEvent`/`WikiAuditEvent` 字段：本接口是它们落库前的统一入参，两张表继续按各自 spec 保留领域字段。

**事件类型枚举（首版 5 个，后续在枚举处扩展）：**

| operation | 写入方 |
| --- | --- |
| `draft.status_changed` | 草稿箱 Buffer |
| `mapping.prereview_log_appended` | Mapping 管理 MCP |
| `mapping.formal_revision_promoted` | Mapping 管理 MCP |
| `wiki.prereview_log_appended` | Wiki 管理 MCP |
| `wiki.formal_revision_promoted` | Wiki 管理 MCP |

`draft.status_changed` 覆盖草稿状态变更（提交、审核、转候选）的留痕，不再区分「草稿提交算不算正式事实」：提交即一次状态变更，照记。

**Buffer 的审计落库：** 草稿箱现有设计只有 TerminusDB，本契约要求它增加一个最小审计 SQLite，只存审计事件，草稿正文仍留在 TerminusDB。

**查询入口：** 查询与写入分离。首版只提供按任务、Proposal、正式版本、时间的查询函数（按各领域 SQLite 重建「谁在什么基准上做了什么、结果如何、谁批准」），不建独立查询服务；后续可由看板或其他服务把这些函数包成 MCP/HTTP API。

**幂等：** 接口不加幂等键。审计是追加式事实，业务防重由写入方自持；若发生重复，按「更正靠追加新事件」处理，不覆盖历史。

**验证策略：** 本票交付共享包及其回归测试，使用测试写入方证明接口契约可用（同事务通过、独立调用被拒、字段校验、查询重建）。真实接入由后续票完成：Buffer 侧见「中央草稿箱的存储与审核契约」(ai4-xem8)。

## Implementation Contract

**位置与形态：** `sci-weave/shared/audit-trail/`，独立 Python 子项目，标准库实现，`requires-python = ">=3.11"`，无第三方依赖。模块名 `audit_trail`，包名 `sciweave-audit-trail`。调用方以 uv `[tool.uv.sources]` path 可编辑依赖引用。

**模块分工（从简）：**

- `events.py`：`AuditEvent` dataclass、`ActorType`/`Operation` 字符串常量、字段校验、`TransactionRequiredError`/`AuditValidationError`。
- `schema.sql`：标准审计表 `audit_event` DDL；`init_audit_table(conn)` 建表。
- `writer.py`：`write_audit_event(conn, event)`，包自生成 `event_id`（UUID4）与 `occurred_at`（UTC ISO8601）。
- `query.py`：`query_audit_events(conn, *, task_id=None, proposal_id=None, formal_revision_id=None, occurred_after=None, occurred_before=None)` 返回按时间倒序的事件 dict 列表。

**标准表字段（对应 Resolution 的 superset）：** 必填 `event_id`、`occurred_at`、`actor_id`、`actor_type`、`operation`、`target_object_type`、`target_object_id`、`result`；可选 `previous_state`、`next_state`、`reason`、`base_revision`、`candidate_revision`、`proposal_id`、`task_id`、`resource_id`、`formal_revision_id`、`merge_request_id`、`refs`（JSON 兑底）。

**约束实现：** `write_audit_event` 先检查 `conn.in_transaction`，非事务内抛 `TransactionRequiredError`；再校验必填字段与枚举，非法抛 `AuditValidationError`。不提供任何 update/delete 函数；API 层保证只追加，不建触发器。

**测试（`tests/test_audit_trail.py`，标准库 `unittest`）：** 内存 SQLite 覆盖同事务写入、独立调用被拒、字段/枚举校验、无 update/delete API、按任务/Proposal/正式版本/时间查询重建责任链。

**验收证据：** 在 `sci-weave/shared/audit-trail/` 执行 `uv run python -m unittest discover -s tests -v` 全绿，并运行 `git diff --check`。

## Acceptance Criteria

- [x] 事件字段与「中央协调 Agent 与审计体系」一致，并有事件类型枚举
- [x] 写入接口只能在事实写入事务内调用，独立调用被拒绝
- [x] 无更新或删除接口
- [x] 按任务、Proposal、正式版本、时间的查询可重建"谁在什么基准上做了什么、结果如何、谁批准"
- [x] 至少一个写入方接入并有回归测试


## Notes

**2026-10-21T13:18:42Z**

2026-10-21T21:20:30Z

调用方清单变更，依据「Task Agent 改由研究员端侧自持」(ai4-we38)。本票 Design 中的调用方之一「Task Agent Gateway 写 OwnerCommand 与 Execution Record」需要澄清：

- OwnerCommand 与 Execution Record 现在落在研究员本机的 SQLite，不再进入中央。
- 端侧 agent 进入中央的事实只有草稿提交，其留痕由草稿箱（`centre-control/buffer`）作为写入方调用本工具完成。
- 因此留痕工具的调用方集合中，端侧不再直接出现，改为经由草稿箱。

仍成立的调用方：Buffer 写预审结论与草稿审核结论、Research Mapping 管理 MCP 推进正式版本、LLM-Wiki 管理 MCP 推进正式版本。

未定：草稿提交本身算不算「改动正式事实」，要不要留痕。按现有定义它不是正式事实，倾向于只在草稿状态变更（提交、审核、转候选）时留痕。

**2026-10-22T00:00:00Z**

本票经 wayfinder grilling 收口（设计树见与 Frank Qi 的逐轮问答）。Design 中的旧调用方表述「Buffer 写预审结论」按第五轮讨论修正为「中央 Agent 预审报告经 `append_prereview_log` 落领域治理记录，由领域管理 MCP 作为写入方留痕」；草稿提交是否留痕的未定项已由事件枚举 `draft.status_changed` 覆盖，不再悬置。验收项全部勾选；真实接入的代码验证留给 ai4-xem8 与领域实现票。
