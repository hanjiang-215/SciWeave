---
id: ai4-tg3v
status: open
deps: []
links: [ai4-dybh]
created: 2026-10-22T01:20:55Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-fv1r
tags: [spec, centre-control, audit, ready-for-agent]
---
# 中央留痕工具共享包实现规格

## Problem Statement

中央服务器上的多个组件——草稿箱（Draft Buffer）、Research Mapping 管理 MCP、LLM-Wiki 管理 MCP——在推进正式事实时都需要留下审计痕迹，但各自写各自的，形状不统一，审计链无法按统一口径重建「谁在什么基准上做了什么、结果如何、谁批准」。留痕不是中央 Agent 的私有能力，而是每个写入方在写事实的同一事务里必须调用的公共工具。

## Solution

提供一个仅用 Python 标准库实现的共享包 `audit_trail`，作为所有中央写入方的统一审计接口：一个只追加的写入函数、一张标准审计表、一个只读查询函数。写入方必须在自己 SQLite 事务内调用；审计事件只追加、不可改不可删；Mapping、Wiki、Buffer 各自落自己的审计 SQLite，接口形状统一但存储不共享，守住领域隔离。

## User Stories

1. As a 草稿箱写入方, I want 在草稿状态变更的同一事务里追加一条审计事件, so that 草稿提交、审核、转候选的责任链可追溯。
2. As a Research Mapping 管理 MCP 写入方, I want 在推进 Formal MappingRevision 的同一事务里追加审计, so that 记录谁批准了哪条路线变化。
3. As a LLM-Wiki 管理 MCP 写入方, I want 在推进 Formal WikiRevision 的同一事务里追加审计, so that 记录 Wiki 正式化责任链。
4. As a 领域管理 MCP 写入方, I want 在 append_prereview_log 落库时同事务留痕, so that 中央 Agent 的预审报告追加也进入审计链。
5. As a Project Owner, I want 按任务、Proposal、正式版本、时间查询审计事件, so that 重建「谁在什么基准上做了什么、结果如何、谁批准」。
6. As a 审计查询者, I want 查询只读且与写入分离, so that 审计视图不会被写入入口污染或绕过。
7. As a 写入方开发者, I want 在没开事务时调用写入被明确拒绝, so that 不会产生「事实已改但没留痕」的记录。
8. As a 写入方开发者, I want 字段缺失或枚举非法时立刻报错, so that 坏数据进不了审计链。
9. As a 领域实现者, I want Mapping 与 Wiki 的审计存储彼此隔离, so that 符合领域隔离约束、不跨域共享审计链。
10. As a 领域实现者, I want 统一接口字段是既有 MappingAuditEvent/WikiAuditEvent 的 superset, so that 已关闭规格不被推翻。
11. As a 端侧研究者或 Agent 托管方, I want 不直接触碰中央留痕接口而由草稿箱统一留痕, so that 端侧不新增中央耦合。
12. As a 后续接入方, I want 以 uv 可编辑依赖引用共享包, so that 不用复制代码也能用同一套接口。

## Implementation Decisions

- 共享包命名 `sciweave-audit-trail`，模块 `audit_trail`，`requires-python >= 3.11`，仅标准库，无第三方依赖。
- 包结构从简：事件模型、标准审计表 DDL 与建表函数、写入函数、查询函数。
- 唯一写入入口 `write_audit_event(conn, event)`：接受调用方自己的 `sqlite3.Connection` 与一条 `AuditEvent`。
- 包不自开连接；先校验连接处于事务内，否则抛 `TransactionRequiredError`；再校验必填字段与枚举，非法抛 `AuditValidationError`。
- `event_id`（UUID4）与 `occurred_at`（UTC ISO8601，秒精度）由包生成，调用方不可传。
- 标准审计表 `audit_event`：必填 `event_id`、`occurred_at`、`actor_id`、`actor_type`、`operation`、`target_object_type`、`target_object_id`、`result`；可选 `previous_state`、`next_state`、`reason`、`base_revision`、`candidate_revision`、`proposal_id`、`task_id`、`resource_id`、`formal_revision_id`、`merge_request_id`、`refs`（JSON 兜底）。
- `actor_type` 枚举：`human` / `agent` / `system`。
- `operation` 首版枚举 5 个：`draft.status_changed`（草稿箱）、`mapping.prereview_log_appended`、`mapping.formal_revision_promoted`、`wiki.prereview_log_appended`、`wiki.formal_revision_promoted`。
- `result` 为自由文本，不建枚举；建议值如 `accepted` / `rejected` / `succeeded` / `failed`。
- 查询入口 `query_audit_events(conn, *, task_id, proposal_id, formal_revision_id, occurred_after, occurred_before)`：只读，按时间倒序返回事件字典列表；`refs` 以 JSON 往返。
- 只追加：不提供任何 update/delete 函数；API 层保证，不建数据库触发器。
- 不加幂等键：审计是追加式事实，业务防重由写入方自持，重复由「更正靠追加新事件」处理。
- 存储隔离：Mapping、Wiki、Buffer 各自持有审计 SQLite；接口统一，存储不共享。草稿箱需新增一个最小审计 SQLite（只存审计事件，草稿正文仍在 TerminusDB）。
- 调用方接入：草稿箱写 `draft.status_changed`；Research Mapping 管理 MCP 写 `mapping.formal_revision_promoted` 与 `mapping.prereview_log_appended`；LLM-Wiki 管理 MCP 写 `wiki.formal_revision_promoted` 与 `wiki.prereview_log_appended`。端侧不直接调用。

## Testing Decisions

- 唯一测试 seam 是 `audit_trail` 包公共 API：`init_audit_table`、`write_audit_event`、`query_audit_events`。
- 测试用内存 SQLite，只验证外部行为：同事务写入成功且可查回、事务外调用被 `TransactionRequiredError` 拒绝、非 Connection 类型被拒、字段缺失/枚举非法抛 `AuditValidationError`、无 update/delete API、按任务/Proposal/正式版本/时间过滤与倒序、`refs` JSON 往返、全部 operation 枚举可写。
- 测试风格与仓库现有 Python 子项目一致：标准库 `unittest`，`uv run python -m unittest discover`。
- 不测试内部实现细节（如 SQL 语句形态）。

## Out of Scope

- 不建 MCP 工具或 HTTP API 服务；写入口保持进程内函数，不暴露给 Agent 自由调用。
- 不接入任何领域代码：Buffer、Research Mapping 管理 MCP、LLM-Wiki 管理 MCP 的真实接入由各自票完成。
- 不建独立查询服务。
- 不共享审计存储：Mapping/Wiki/Buffer 各自落库，不建中央审计库。
- 不加幂等键、不建数据库触发器防 update/delete。
- 不定义执行侧（端侧 Gateway、Execution Record）审计——端侧不进中央。

## Further Notes

- 本规格的决策来源是已关闭的「中央服务留痕工具：写入方统一调用的审计接口」的 Resolution。
- 字段是「中央协调 Agent 与审计体系」字段清单与 MappingAuditEvent / WikiAuditEvent 已关闭规格的 superset，不推翻既有领域规格。
- 术语以根 `GLOSSARY.md` 为准：AuditEvent、领域隔离、只追加、Formal Revision。

