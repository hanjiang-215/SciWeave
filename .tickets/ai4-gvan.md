---
id: ai4-gvan
status: open
deps: []
links: [ai4-tg3v, ai4-dybh, ai4-jnkn]
created: 2026-10-22T05:20:54Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-tg3v
tags: [audit, centre-control, implementation, enhancement, ready-for-agent]
---
# 留痕包迁移到 centre-control 并改造为接口层调用账本

把 `sci-weave/shared/audit-trail` 迁到 `sci-weave/centre-control/shared/audit-trail`，并按新契约（见父票「中央留痕工具共享包实现规格」）把「正式事实变更审计」改造成「接口层对外调用账本」。

## Problem Statement

现有共享包是存储层审计：`write_audit_event(conn, event)` 校验 `conn.in_transaction`，要求领域模块在自己的 SQLite 事务里调用。语义是「正式事实变更」，枚举是 `formal_revision_promoted` 一类。全部下游零引用。

现行决策改为接口层账本后，这个包的形态整体不再成立：事件形状、写入时机、事务假设、位置、枚举都不适用。

## What to build

1. **迁目录**：`sci-weave/shared/audit-trail` → `sci-weave/centre-control/shared/audit-trail`。用 `git mv` 保留历史。
2. **改事件形状**为调用账本（见父票 Implementation Decisions）：`caller_id`、`channel_id`、`caller_type`、`service`、`tool`、`phase`、`result`、`error_code`、`duration_ms`、`args_digest`、`target_object_type`、`target_object_id`、`refs`。删除 `previous_state`、`next_state`、`base_revision`、`candidate_revision`、`formal_revision_id`、`merge_request_id`、`operation`、`actor_id`、`actor_type`。
3. **改写入接口**：不再要求 `conn.in_transaction`；包接收一个 `sqlite3.Connection`（或路径），自己用 `BEGIN IMMEDIATE` + `commit` 完成单条追加。删除 `TransactionRequiredError`。
4. **两阶段写入 helper**：`record_call(...)` 上下文管理器或 `begin_call`/`finish_call` 一对函数，供写工具使用；读工具用单条记录。
5. **改查询接口**：按 `caller_id`、`channel_id`、`service`、`tool`、`target_object_id`、`result`、时间区间过滤，时间倒序。
6. **改测试**：删掉「事务外调用被拒」类断言，新增跨调用可写、两阶段配对可查、`args_digest` 不留正文、fail-closed 行为可用测试替身证明。
7. **改 README**：示例必须能直接跑通（现有示例因 `with conn:` 不开事务而失败）。

## 不在本票范围

- 不接任何真实服务。research-map / research-wiki / buffer 的 MCP 层尚不存在，接入由各自实现票在 MCP 层落地时完成。
- 不实现装饰器或中间件本身。装饰器写在接入方（MCP 层），本票只提供可被装饰器调用的函数与上下文管理器。
- 不改 `sci-weave/task-agent` 的 `audit_events`。

## Acceptance Criteria

- [ ] 目录迁移完成，`git log --follow` 能看到原文件历史，仓库内无残留 `sci-weave/shared/` 引用
- [ ] `pyproject.toml` 包名与模块名保持 `sciweave-audit-trail` / `audit_trail`，`requires-python` 与依赖不变（仍为标准库）
- [ ] 事件模型与表结构换成调用账本字段，旧字段全部删除
- [ ] 写入不再要求调用方处于事务内，包自己管理单条追加的事务
- [ ] 提供写工具用的两阶段 helper，且能查出「只有 invoked 没有 completed」的残缺调用
- [ ] `args_digest` 为参数摘要，任何入参正文不落审计库
- [ ] 查询支持按 `caller_id` / `channel_id` / `service` / `tool` / `target_object_id` / `result` / 时间区间过滤，时间倒序
- [ ] README 示例直接可运行，不出现 `with conn:` 误用
- [ ] `uv run python -m unittest discover -s tests -v` 全绿，`git diff --check` 通过
- [ ] `docs/TECH_STACK.md` 的共享代码规则同步更新（见父票）

## Notes

**2026-10-22T13:20:00Z**

来源：2026-10-22 与 Frank Qi 的三轮 grilling 决策。父票已改为接口层调用账本，本票承载其代码落地。

现状事实（2026-10-22）：

- 共享包全仓库零引用，没有任何 `pyproject.toml` 依赖 `sciweave-audit-trail`，改形状无下游要跟。
- 旧包 `writer.py:29` 的 `init_audit_table` 用 `conn.execute(_SCHEMA_SQL)`，只支持单语句 DDL，加索引即抛 `ProgrammingError`；改造时一并解决（拆成逐语句执行或改用 `executescript`）。
- `write_audit_event` 实际返回 `event_id`（`writer.py:41`），与旧票写的 `-> None` 不一致；新接口不返回 id，由调用方传入的关联键查询。
