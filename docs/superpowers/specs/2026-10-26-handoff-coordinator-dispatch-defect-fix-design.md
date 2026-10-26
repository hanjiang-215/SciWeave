# 交接协调核心派发缺陷修复实现规格

- 日期：2026-10-26
- 关联工单：[`ai4-10ja`](../../../.tickets/ai4-10ja.md)
- 上游决策：[`ai4-te1v`](../../../.tickets/ai4-te1v.md)、[`ai4-zc85`](../../../.tickets/ai4-zc85.md)（均已关闭）
- 状态：施工前规格已收敛

## 目的与边界

`sci-weave/centre-control/coordinator` 的核心状态机有七个已复现的缺陷。`ai4-1y6q` 的 9 项测试全部通过，但没有覆盖这些场景，所以它们在测试绿的情况下依然存在。

本规格只改 `coordinator` 子项目。不改 `shared/message-envelope/`（当时尚未实现），不写任何真实适配器，不动 Redpanda 与 email-service 的调用实现。

> 落地说明（2026-10-27）：`shared/message-envelope/` 已经落地在 `sci-weave/centre-control/shared/message-envelope/`，承接票 `ai4-3zxu`、`ai4-sv1u` 均已关闭。下文保留为设计记录。

## 为什么测试绿着还坏着

现有 9 项测试喂的是「一个域、一个版本、一个节点、一个执行者」这类最顺的输入。七个缺陷全部出现在组合边界上：多个版本、多个执行者、零入边、多次重试。

这不是测试写得差，是覆盖面的问题。修完之后每个缺陷都要留下一个当初会失败的用例。

## 七个缺陷与修法

### 1. 重复派发

去重键含触发版本：

```text
当前：mapping_domain_id:task_node_id:target_node_version_ref:message_type:trigger_revision_id
应为：mapping_domain_id:task_node_id:target_node_version_ref:message_type
```

每来一个新正式版本，同一节点版本被重新派发一次，Task Agent 重复执行。

为什么去掉的是触发版本而不是节点版本：一个派发的语义是「这个节点的这个版本该开工了」。它跟由哪个正式版本触发无关——触发者可以有无数个，该做的事只有一件。

### 2. `done` 退回 `waiting`

`upsert_pending_handoff` 无条件 `UPDATE ... SET status`。上游升版本后，下游已 `done` 的记录被覆盖回 `waiting`，已派发事实丢失，随后再次派发。

允许的迁移：

```text
waiting → ready → dispatched_unknown → done
任意非终结态 → superseded / failed
```

`done` 是终结态，重算不得回退。

**1 和 2 必须同时修。** 只改去重键，`done` 仍会被覆盖回 `waiting`，新触发版本下依然重复派发；只加状态守卫，同一触发版本重放仍会重复。二者缺一，「三个正式版本只派发一次」这条验收就过不了。

### 3. 多执行者误判为不可用

两处写死 `node.executor_refs[0]`。`executor_refs` 允许引用协作集合，第一个离线而第二个在线时被误判为「无可用执行者」并转人工。

改为按声明顺序取第一个可用者。顺序是配置者表达偏好的方式，不应该被随机化或并发探测取代。

`target_agent_id` 记实际选中者；`executor_ref_snapshot` 记完整快照。

### 4. 无入边节点被自动派发

`incoming` 为空时 `all([]) == True`，任何正式版本发布都会自动派发根节点，绕过 PO 的显式派分。

「无入边」不是条件平凡满足，而是不满足可自动派发条件。根任务是 PO 的决定，不是图结构的推论。

同时补齐 `dispatch_root_task`（当前 `src/` 与 `tests/` 均无实现）：PO 显式派发某个根节点，幂等，产出与自动派发相同的 `task_handoff_ready`。

### 5. `dead` 状态从未落地

`DISPATCH_DEAD` 只在 import 里出现，没有任何写入路径。`max_attempts` 也只被构造、从不比较，失败会无限重试。

重试前比较 `attempt_count >= max_attempts`，达到则写 `dead`，不再自动重放。`dead` 保留在可观察范围内，供人工经运维查询处理。

默认值由 `3` 改为 `5`，配置、README、`.env.example` 三处一起改。三处不一致比数值本身更麻烦——运维按 README 配置，实际行为却不同。

### 6. 人工通知收件人取值错误

四处传 `mapping_domain_id`，而 email-service 要的是 `principal_id`。传域 ID 解析不到收件人。

收件人由通知类型决定，不由调用方选择：

| 场景 | `notification_kind` | 收件人 |
| --- | --- | --- |
| `executor_refs` 为空 | `workflow_binding_required` | 该节点 `task_owner_id` |
| `executor_refs` 指向未登记的 `agent_id` | `workflow_load_failed` | 该节点 `task_owner_id` |
| 已注销、无可用实例、或只配置人工处理 | `agent_unavailable` | 该节点 `task_owner_id` |
| 派发成功的节点无后继 | `task_terminal_summary` | `FormalSnapshot.latest_published_by` |

四种场景三种 kind，因为它们要求收件人做的事不同：绑一个 Workflow、修一个配错的 `agent_id`、或者自己上手。合并成一种，邮件正文就说不出下一步该干什么。

一条通知只有一个收件人。

`task_owner_id` 缺失表示数据损坏：不猜收件人、不生成通知、保留 `waiting`，记录 `recipient_unresolved:task_owner_id_missing`。宁可不动，也不能把任务通知给一个随机的人。

`FormalSnapshot.latest_published_by` 命名见 [ADR-0004](../../adr/0004-po-recipient-from-latest-approver.md)：它回答「最近一次批准正式版本的人」，不是「被任命的负责人」。

发送前经 Registry 校验 `principal_id` 存在且 `active`；不通过则不建 dispatch、记错误、保持 `waiting`。**Registry 不可用时 fail-open 照发**——校验是减少错发，不是阻止正常投递；因为它挂了就停掉整条通知链路，代价大于收益。

### 7. 快照错误路径两处不一致

`startup_scan` 遇快照错误静默 `continue`；`_retry_dispatch` 遇同样错误写 `result_unknown`。同一个失败在两个入口产生两种状态，事后无法判断「是真没派发」还是「读不到快照」。

统一口径：`unavailable` / `inconsistent` 视为可重试，保留既有事实，等待下次事件或启动扫描；只有确定不可恢复时才转 `failed`。

## 实现顺序

七个缺陷里五个互不依赖，但第 6 个要先加接口：`PrincipalDirectoryPort` 注入构造函数会改所有测试的组装函数。因此先做一次**无行为变更的扩展**：新增快照字段、新增端口、补齐 `HandoffReadyMessage` 的载荷字段，现有测试照绿。

之后五个修复各自独立，可并行。

## 不做什么

- 不实现任何真实适配器。快照、Registry、Redpanda、email-service 的适配器分别是 `ai4-edrp` 与后续票。
- 不投影 `dependency_kind` / `activation_condition` / `required_outputs` / `blocks_until`。这四个字段在 `DependencyEdgeDoc` 中整体缺失，属于判定逻辑扩充，需要独立决策。
- 不改 `shared/message-envelope/`。
