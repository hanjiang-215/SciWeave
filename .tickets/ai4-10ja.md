---
id: ai4-10ja
status: open
deps: [ai4-te1v]
links: [ai4-zc85, ai4-1y6q]
created: 2026-10-26T07:11:28Z
type: task
priority: 1
assignee: Frank Qi
parent: ai4-p5f3
tags: [implementation, centre-control, coordinator, message-queue]
---
# 修复 handoff coordinator 派发幂等与执行者选择缺陷

## Background

2026-10-26 用 Fake ports 把 `sci-weave/centre-control/coordinator` 的 `CoordinatorService` 当沙箱跑了一遍，用实测结果反查协议缺口。协议层结论已回写 `ai4-te1v`；代码缺陷由本票承接。

`ai4-1y6q` 的 9 项测试全部通过，但没有覆盖下面这些场景，所以这些缺陷在测试绿的情况下依然存在。

## 实测证据

```text
同一节点版本、三个 revision      → 派发 3 次（应 1 次）
done 后再次重算                  → 退回 waiting
executor_refs=(a1,a2)、仅 a2 在线  → 判定无可用执行者（应派发给 a2）
无入边根节点 + 任意正式版本发布    → 自动派发 1 次（应 0 次）
DISPATCH_DEAD                   → 全仓库只被 import，从未写入
recipients                      → 传 mapping_domain_id，非 principal_id
```

复现方式：在 `coordinator/` 下用 `PYTHONPATH=src` 导入 `CoordinatorService`，注入 Fake snapshot / publisher / notification 端口，按上述场景调用 `on_formal_revision_published` 与 `on_task_completed`，观察 `list_dispatches` 与 Fake publisher 的累计条数。

## 缺陷清单

### 1. 重复派发

`_dedupe` 的键含触发 revision：

```text
当前：mapping_domain_id:task_node_id:target_node_version_ref:message_type:trigger
应为：mapping_domain_id:task_node_id:target_node_version_ref:message_type
```

每来一个新正式版本，同一节点版本会被重新派发一次，Task Agent 重复执行。按 `ai4-te1v`「重复派发的去重」去掉 `trigger_revision_id`。

### 2. `done` 退回 `waiting`

`upsert_pending_handoff` 无条件 `UPDATE ... SET status`。上游升版本后，下游已 `done` 的 `PendingHandoff` 被覆盖回 `waiting`，已派发事实丢失，随后触发再次派发。

按 `ai4-zc85` 的状态迁移校验补守卫：只允许 `waiting → ready → dispatched_unknown → done` 以及任意非终结态 → `superseded` / `failed`；`done` 是终结态，重算不得回退。

### 3. 多执行者误判为不可用

`_evaluate_snapshot` 与 `_recompute_downstream` 两处都写死 `node.executor_refs[0]`。`ai4-r3so` 允许 `executor_refs` 引用协作集合，第一个离线而第二个在线时会被误判为「无可用执行者」并转人工。

按 `ai4-te1v`「executor_refs 多值选择」改为按声明顺序取第一个可用者；全部不可用才转人工。`target_agent_id` 记实际选中者，`executor_ref_snapshot` 记完整快照。

### 4. 无入边节点被自动派发

`incoming` 为空时 `all([]) == True`，导致任何正式版本发布都会自动派发根节点，绕过 PO 的 `dispatch_root_task`。

按 `ai4-te1v`「根任务派发」显式排除零入边节点：「无入边」是不满足可自动派发条件，不是条件平凡满足。同时补齐 `dispatch_root_task` 的发布端口实现（当前 `src/` 与 `tests/` 均无实现）。

### 5. `dead` 状态从未落地

`DISPATCH_DEAD` 只在 `service.py:18` 被 import、在 `store.py:21` 被定义，没有任何写入路径。`CoordinatorConfig.max_attempts` 也只被构造、从不比较，`failed` 会无限重试。

- 重试前比较 `attempt_count >= max_attempts`，达到则写 `dead`，不自动重放。
- `SCIWEAVE_COORDINATOR_MAX_ATTEMPTS` 默认值由 `3` 改为 `5`（`config.py:60`），同步 `README.md:19` 与 `.env.example`。
- `dead` 记录保留在 `list_dispatches` 可观察范围内，供人工经运维查询处理。

### 6. 人工通知收件人取值错误

`service.py` 四处 `recipients=(snapshot.mapping_domain_id,)`。`ai4-f985` 要求 `recipients` 是 `principal_id`，email-service 用 Registry 只读联系人接口解析邮箱；传 domain id 解析不到收件人。

需要明确 `PendingHandoff` / 节点上「该通知谁」的来源，再由调用点取对应 `principal_id`。来源不明确时本票不臆造字段，先向 `ai4-f985` 的 assignee 确认。

### 7. 快照错误路径两处不一致

`startup_scan` 遇 `SnapshotUnavailableError` / `SnapshotInconsistentError` / `NoSuchRevisionError` 时 `continue`（静默跳过）；`_retry_dispatch` 遇同样错误写 `DISPATCH_RESULT_UNKNOWN`。同一个失败在两个入口产生两种状态。

按 `ai4-te1v`「统一消息信封」与恢复模型统一口径：`unavailable` / `inconsistent` 视为可重试，保留既有事实并等待下次事件或启动扫描；只有确定不可恢复时才转 `failed`。具体归并方式以本票实现时与 `ai4-zc85` 对齐为准。

## Acceptance Criteria

- [ ] 同一节点版本连续三个正式版本发布，只产生 1 条 `HandoffDispatch` 和 1 条 `task_handoff_ready`。
- [ ] `PendingHandoff` 进入 `done` 后，上游版本升级或再次重算都不把它改回 `waiting`。
- [ ] `executor_refs=(a1, a2)` 且仅 `a2` 可用时，派发给 `a2`，不产生人工通知。
- [ ] 全部 `executor_refs` 不可用时，不发布 `task_handoff_ready`，保留 `waiting` 并产生 `human_notification_intent`。
- [ ] 无入边根节点在任意正式版本发布后不自动派发；`dispatch_root_task` 可显式派发且幂等。
- [ ] `attempt_count` 达到 `max_attempts` 的 dispatch 写入 `dead`，不再被重试。
- [ ] `MAX_ATTEMPTS` 默认值为 `5`，`README.md` 与 `.env.example` 一致。
- [ ] 人工通知的 `recipients` 取 `principal_id`，不取 `mapping_domain_id`。
- [ ] 快照不可读时，`startup_scan` 与 `_retry_dispatch` 的状态处置一致。
- [ ] 上述场景全部转成测试用例，与 `ai4-1y6q` 既有的 9 项测试一起通过。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 本票只改 `coordinator`，不动 `shared/message-envelope/`（尚未实现）与 Redpanda 适配层。
- `dependency_kind` / `activation_condition` / `required_outputs` / `blocks_until` 四个字段在 `ports.py` 的 `DependencyEdgeDoc` 中整体缺失，属独立的判定逻辑扩充，不在本票范围。
- 缺陷 6 依赖 `ai4-f985` 的收件人来源定义，若届时仍不明确则先只记录、不改调用点。
