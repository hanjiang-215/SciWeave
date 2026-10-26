---
id: ai4-edrp
status: open
deps: [ai4-2raq]
links: [ai4-2982, ai4-1y6q, ai4-10ja]
created: 2026-10-26T07:36:06Z
type: feature
priority: 1
assignee: Frank Qi
parent: ai4-p5f3
tags: [implementation, centre-control, coordinator, adapter]
---
# handoff coordinator 快照适配器接入 research-map 正式快照

## Background

`coordinator` 至今没有任何真实适配器。[`src/main.py`](../sci-weave/centre-control/coordinator/src/main.py) 的全部内容是：读配置、开 SQLite、打两行日志、关连接。`FormalSnapshotPort`、`AgentAvailabilityPort`、`HandoffPublisherPort`、`NotificationPublisherPort` 四个 Port 只有 Protocol 定义，没有任何实现类。

缺口不是遗忘，而是四个口子各自卡在不同上游，而「接入」这一步从未被立成票。`ai4-1y6q` 当时写的是「真实 MCP/Redpanda 适配器待接口票 `ai4-2982` 和消息语义收敛后接入」，此后无人接手。

本票只做**其中的快照适配器**，因为它是四个里唯一上游已清零的：`ai4-2982` 已关闭，`get_formal_mapping_at_revision` 已实现并通过 115 项测试，返回的 `documents` 是原始 TerminusDB 文档。它不需要 Redpanda、不需要信封包、不需要 email-service。

其余三个仍然等待，不在本票范围：

| Port | 等待的上游 |
| --- | --- |
| `AgentAvailabilityPort` | `ai4-1kls`（open）冻结 Registry MCP |
| `HandoffPublisherPort` | `shared/message-envelope/` 尚未实现 |
| `NotificationPublisherPort` | `ai4-f985` 已定，但依赖本票提供 `task_owner_id` |

## Why it matters

没有这个适配器，`TaskNodeDoc.task_owner_id` 永远是 `None`，`ai4-10ja` 修好的人工通知收件人逻辑依然是死代码。本票是那条链路真正生效的前提。

同时它给 `ai4-10ja` 提供真实验证手段：七个缺陷目前全靠 Fake ports 断言，长效性差；有了适配器，至少「节点投影」这一段能对着真文档验。

## Scope

实现 `FormalSnapshotPort`，通过 research-map 管理 MCP（Streamable HTTP `POST /mcp`）的 `get_formal_mapping_at_revision` 读取正式快照，把 `documents` 投影为 `FormalSnapshot`。

### 文档到契约的投影

TerminusDB 文档与 `ports.py` 的 dataclass 形状不一致，适配器负责翻译：

```text
节点  @type = "TaskNode"            task_node_id  ← logical_id
       @id   = "TaskNode/<version>"  version_id    ← version_id
                                    executor_refs ← executor_refs
                                    task_owner_id ← task_owner_id

边    @type = "DependencyEdge"       edge_id        ← logical_id
       source_node_version_ref = {logical_id, version_id}
       target_node_version_ref = {logical_id, version_id}
```

边的两个嵌套引用必须**拍平**为 `source_node_id` / `source_version_id` / `target_node_id` / `target_version_id`，因为 `DependencyEdgeDoc` 是扁平结构。

### 明确丢弃的字段

`DependencyEdgeDoc` 目前没有 `dependency_kind`、`activation_condition`、`required_outputs`、`blocks_until`，而文档里这四项是必填（`candidate_submission.py` 校验）。本票**不投影**它们。

这是有意的范围控制，不是遗漏：`ai4-te1v` 规定 `dependency_kind` 的判定逻辑属于另一张实现票，把字段提前塞进契约会让两张票焊死。

**代码中必须留显式注释**说明这四个字段被丢弃且指向后续票号，不得静默丢弃。将来补投影时，改动点应当只有这一处。

## Acceptance Criteria

- [ ] `FormalSnapshotPort` 有实现类，通过 MCP 调用 `get_formal_mapping_at_revision`。
- [ ] `TaskNode` 文档投影出 `task_node_id`、`version_id`、`executor_refs`、`task_owner_id`。
- [ ] `DependencyEdge` 文档的两个嵌套引用拍平为四个扁平字段。
- [ ] `dependency_kind` / `activation_condition` / `required_outputs` / `blocks_until` 不被投影，且代码中有显式注释与后续票号。
- [ ] `no_such_revision` / 服务不可用 / 响应结构非法，分别映射到既有的 `NoSuchRevisionError` / `SnapshotUnavailableError` / `SnapshotInconsistentError`，不新增错误类型。
- [ ] 用固定 fixture 文档做单元测试，覆盖节点投影、边拍平、空图、非法文档和三种错误映射。
- [ ] 真连 MCP 的集成测试默认跳过，需要显式环境变量才运行；跳过时不影响 `pytest -q` 通过。
- [ ] MCP 地址、端口、令牌从环境变量读取，不硬编码；`.env.example` 与 `README.md` 同步。
- [ ] 在 fer 记录验证命令、结果和提交哈希。

## Notes

- 传输方式与鉴权边界由 `ai4-2982` 定死：走 research-map 管理 MCP 的 `POST /mcp`，不另设内部 HTTP 接口，不直连 Research Mapping 的 SQLite 或 TerminusDB，不因「同进程」豁免鉴权。地址经 `SCIWEAVE_MAPPING_MCP_*` 配置。
- `FormalSnapshot` 需要新增 `latest_published_by`，供 `task_terminal_summary` 取收件人。它来自 `formal_mapping_revision.published_by`，不是 `documents` 里的字段，因此需要 `ai4-2raq` 把它加进 MCP 返回。命名依据见 [ADR-0004](../docs/adr/0004-po-recipient-from-latest-approver.md)。
- 本票不实现错误重试策略。适配器只做一次调用并抛出既有错误类型，重试由 `CoordinatorService` 的恢复模型负责。
