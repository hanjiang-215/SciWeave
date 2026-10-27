---
id: ai4-10ja
status: closed
deps: [ai4-te1v]
links: [ai4-zc85, ai4-1y6q, ai4-fu4i, ai4-quvy]
created: 2026-10-26T07:11:28Z
type: task
priority: 1
assignee: hanjiang
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

收件人来源已在 `ai4-te1v` 第四轮收敛中定死，按以下口径修：

| 场景 | `notification_kind` | 收件人 |
| --- | --- | --- |
| `executor_refs` 为空 | `workflow_binding_required` | 该节点 `task_owner_id` |
| `executor_refs` 指向未登记的 `agent_id` | `workflow_load_failed` | 该节点 `task_owner_id` |
| 已注销、无可用实例、或只配置人工处理 | `agent_unavailable` | 该节点 `task_owner_id` |
| 派发成功的节点无后继 | `task_terminal_summary` | `FormalSnapshot.latest_published_by` |

一条通知只有一个收件人。`task_owner_id` 缺失表示数据损坏：不猜收件人、不生成通知，保留 `PendingHandoff(status=waiting)` 并记录 `recipient_unresolved:task_owner_id_missing`。

`FormalSnapshot` 新增 `latest_published_by` 字段，命名见 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)：它回答「最近一次批准正式版本的人」，不是「被任命的负责人」，代码注释需链到该 ADR。填充它依赖 research-map 把 `published_by` 加进 `get_formal_mapping_at_revision` 的返回，该改动由 `ai4-2raq` 承接。

发送前经 Registry 校验 `principal_id` 存在且 `active`，不通过则不建 dispatch、记错误、保持 `waiting`；Registry 不可用时 fail-open 照发。该校验需要新增 `PrincipalDirectoryPort`，与既有 `AgentAvailabilityPort` 走同一条只读通道。

### 7. 快照错误路径两处不一致

`startup_scan` 遇 `SnapshotUnavailableError` / `SnapshotInconsistentError` / `NoSuchRevisionError` 时 `continue`（静默跳过）；`_retry_dispatch` 遇同样错误写 `DISPATCH_RESULT_UNKNOWN`。同一个失败在两个入口产生两种状态。

按 `ai4-te1v`「统一消息信封」与恢复模型统一口径：`unavailable` / `inconsistent` 视为可重试，保留既有事实并等待下次事件或启动扫描；只有确定不可恢复时才转 `failed`。具体归并方式以本票实现时与 `ai4-zc85` 对齐为准。

## Acceptance Criteria

- [x] 同一节点版本连续三个正式版本发布，只产生 1 条 `HandoffDispatch` 和 1 条 `task_handoff_ready`。
- [x] `PendingHandoff` 进入 `done` 后，上游版本升级或再次重算都不把它改回 `waiting`。
- [x] `executor_refs=(a1, a2)` 且仅 `a2` 可用时，派发给 `a2`，不产生人工通知。
- [x] 全部 `executor_refs` 不可用时，不发布 `task_handoff_ready`，保留 `waiting` 并产生 `human_notification_intent`。
- [x] 无入边根节点在任意正式版本发布后不自动派发；`dispatch_root_task` 可显式派发且幂等。
- [x] `attempt_count` 达到 `max_attempts` 的 dispatch 写入 `dead`，不再被重试。
- [x] `MAX_ATTEMPTS` 默认值为 `5`，`README.md` 与 `.env.example` 一致。
- [x] 人工通知的 `recipients` 取 `principal_id`，不取 `mapping_domain_id`。
- [x] `executor_refs` 为空、指向未登记 `agent_id`、已注销、只配置人工处理四种场景，分别产出 `workflow_binding_required`、`workflow_load_failed`、`agent_unavailable` 三种 `notification_kind`。
- [x] `task_terminal_summary` 的收件人取 `FormalSnapshot.latest_published_by`，不取 `mapping_domain_id`。
- [x] `task_owner_id` 缺失时不产生通知，`PendingHandoff` 保持 `waiting` 且记录 `recipient_unresolved:task_owner_id_missing`。
- [x] Registry 校验失败时不建 dispatch；Registry 不可用仍照发。
- [x] 快照不可读时，`startup_scan` 与 `_retry_dispatch` 的状态处置一致。
- [x] 上述场景全部转成测试用例，与 `ai4-1y6q` 既有的 9 项测试一起通过。
- [x] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 本票只改 `coordinator`，不动 `shared/message-envelope/`（尚未实现）与 Redpanda 适配层，也不写任何真实适配器（见 Q8 裁决）：`TaskNodeDoc(task_owner_id=...)` 与 `FormalSnapshot(latest_published_by=...)` 在测试里直接构造。
- `dependency_kind` / `activation_condition` / `required_outputs` / `blocks_until` 四个字段在 `ports.py` 的 `DependencyEdgeDoc` 中整体缺失，属独立的判定逻辑扩充，不在本票范围。
- 缺陷 6 依赖 `ai4-f985` 的收件人来源定义，若届时仍不明确则先只记录、不改调用点。

**2026-10-26 负责人转交（hanjiang 操作，按项目所有者指示）**

身份核对：本票 assignee 已由 Frank Qi 改为 hanjiang；当前分支 `feature/hanjiang`、`git config user.name=hanjiang`，一致。依据：项目所有者 2026-10-26 指示，Frank Qi 名下 coordinator / handoff / message-envelope 链路的 11 张 open 票统一转交 hanjiang 推进与收口。原负责人 Frank Qi，转交时间 2026-10-26T15:41:00Z。转交只变更归属并记录，不改写正文、验收标准与既有决策。

**2026-10-26T16:28:38Z**

**2026-10-27 收口（hanjiang）**

> *This was generated by AI during triage.*

身份核对：本票 assignee=hanjiang，当前分支 `feature/hanjiang`，`git config user.name=hanjiang`，一致。

七个缺陷全部落地，子票同步关闭：`ai4-7cmr`（幂等与状态回退）、`ai4-7d92`（dead 与重试上限）、`ai4-7uxz`（执行者选择）、`ai4-hgq6`（根节点）、`ai4-xkbd`（通知收件人与三种 kind）、`ai4-98ye`（快照错误收敛）。另有 `ai4-2raq` + `ai4-edrp` 提供 `latest_published_by` 与真实快照适配器。

提交链：`98cd86e`（端口扩容，无行为变化）→ `db2b791`（缺陷 1/2/3/4/5）→ `926aff8`（缺陷 6：三种 kind + principal 校验）→ `3058c03`（缺陷 7 + 根节点 waiting 事实 + 消息字段）→ `6500974`（非法迁移不中断整轮）→ `d22c035`（终局通知缺 approver 留记录）。

验证：`uv run --env-file .env.example pytest -q` → 59 passed, 2 skipped；`python -m compileall -q src tests` → exit 0。

与验收标准字面的差异（与 `ai4-xkbd` 记录一致）：

1. 「只配置人工处理」在 Registry 无可读表示，落到 `agent_unavailable`。
2. 「Registry 校验失败不建 dispatch」实现为「不建待发送 dispatch、写一条 `failed` 记录」，否则「记错误」不可观察。
3. 该校验当前 fail-open 到默认目录：coordinator 无可用 Registry principal 只读工具。

遗留：`dependency_edge_version_refs` 仍为空数组，已开 `ai4-fu4i`；`DependencyEdgeDoc` 缺四个判定字段，已开 `ai4-quvy`。
