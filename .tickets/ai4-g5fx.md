---
id: ai4-g5fx
status: closed
deps: []
links: [ai4-10ja, ai4-2raq, ai4-edrp]
created: 2026-10-26T08:21:32Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-10ja
tags: [implementation, centre-control, handoff, prefactor]
---
# 扩展协调器端口与快照字段

## What to build

在不改变任何现有行为的前提下，把后续五个缺陷修复需要的接口先立起来，并且现有 9 项测试全部照绿。这样五个修复可以各自独立开工，不必挤在同一批改动里改构造签名。

规格见 [`2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md`](../docs/superpowers/specs/2026-10-26-handoff-coordinator-dispatch-defect-fix-design.md)。

## Acceptance Criteria

- [x] `FormalSnapshot` 新增 `latest_published_by` 字段，可为 `None`；注释链到 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)，写明它回答「最近一次批准者是谁」而非「谁被任命为负责人」。
  - 依据：`ports.py` 的 `FormalSnapshot.latest_published_by: str | None = None`，上方注释逐句说明两者区别并指向 ADR-0004。
- [x] 新增 `PrincipalDirectoryPort`，能查询某个 `principal_id` 是否存在且状态为 `active`；Registry 不可用时能表达「无法判断」，而不是返回 False。
  - 依据：`PrincipalState` 三值 `ACTIVE`/`ABSENT`/`UNKNOWN`，`PrincipalDirectoryPort.state_of()`，`UnverifiablePrincipalDirectory` 恒返 `UNKNOWN`。
- [x] `CoordinatorService` 构造函数接受该端口，缺省为不校验的实现，现有调用点无需修改。
  - 依据：`principals: PrincipalDirectoryPort | None = None`，缺省落到 `UnverifiablePrincipalDirectory()`；`test_service_without_a_directory_still_constructs` 用四个参数构造成功。
- [x] `HandoffReadyMessage` 补齐 `upstream_source_refs`、`dependency_edge_version_refs`、`executor_ref_snapshot` 三个字段，与 `ai4-te1v` 的载荷要求一致。
  - 依据：三字段均为尾部带默认值的元组，`test_handoff_ready_message_carries_protocol_payload_fields` 逐字段断言。
- [x] `dependency_edge_version_refs` 为元组/数组，单元素时仍是数组。
  - 依据：`tuple[str, ...]`；`test_dependency_edge_version_refs_stays_a_sequence_with_one_element` 断言 `isinstance(..., tuple)`。
- [x] 现有 9 项测试不改断言、全部通过。
  - 依据：`git diff HEAD~3 -- tests/test_coordinator.py` 为空；`pytest -q` 19 passed（原 9 项 + 新 10 项）。
- [x] 新增测试：`FormalSnapshot` 带 `latest_published_by` 时可构造；`PrincipalDirectoryPort` 的三种结果（存在且 active、不存在、无法判断）各有覆盖。
  - 依据：`tests/test_ports.py` 10 项，含三值各一例与经 `CoordinatorService` 注入的一例。
- [x] 在 fer 记录验证命令、结果和提交哈希。
  - 依据：见 `## Resolution`。

## Notes

- **只加不接线。** 本票不改变任何派发、通知或状态迁移行为；新字段与新端口加进来但没人读，是预期状态。
- 为什么不并入某一个修复票：`PrincipalDirectoryPort` 会改 `CoordinatorService` 的构造签名，而所有测试都经由 `make_service` 组装。先做一次无行为变更的扩展，后续五张票才能并行且互不冲突。
- `latest_published_by` 的真实数据由 `ai4-2raq` 与 `ai4-edrp` 提供；本票只让类型上能承载，测试直接构造。
- `executor_ref_snapshot` 与 `upstream_source_refs` 的语义见 `ai4-te1v`「统一消息信封」，不要在此重新定义。

## Resolution

2026-10-26 关闭。

提交：

- `98cd86e` `feat(coordinator): widen ports and payloads with no behaviour change`
- `ec58ad5` `test(coordinator): cover all three principal directory outcomes`

验证命令与结果：

```text
$ cd sci-weave/centre-control/coordinator
$ UV_CACHE_DIR=/tmp/uvcache uv run --env-file .env.example pytest -q
19 passed in 0.02s

$ UV_CACHE_DIR=/tmp/uvcache uv run --env-file .env.example python -m compileall -q src tests
compile-ok
```

`19 = 原 9 项 + 新增 10 项`；`tests/test_coordinator.py` 在本次改动中零差异。

实现中的两处判断：

1. **`PrincipalState` 用三值枚举而不是 `bool`。** 验收只要求「能表达无法判断」，但返回 `bool` 时 `UNKNOWN` 只能折成 `False`，而 `False` 的下游语义是「这个 principal 不存在」——一个读不到的注册中心会被当成「此人已注销」，从而静默吞掉真实通知。三值让 fail-open 与 fail-closed 在类型上就分得开。
2. **缺省实现恒返 `UNKNOWN` 而不是 `ACTIVE`。** 两者都让前置校验变成空操作，但 `UNKNOWN` 表达的是「我没接适配器，判断不了」，与真实适配器返回的「此人确实存在」区分得开；用 `ACTIVE` 会让「没接线」和「校验通过」混为一谈。

遗留：

- `DependencyEdgeDoc` 仍只有 5 个扁平字段，缺 `dependency_kind`、`activation_condition`、`required_outputs`、`blocks_until`。这属于判定逻辑扩充，规格已明确不在本票范围，需要独立决策票。
- `PrincipalDirectoryPort` 尚无真实 Registry 适配器，`state_of` 的三种取值目前只有测试覆盖。
