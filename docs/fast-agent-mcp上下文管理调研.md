# fast-agent-mcp 上下文管理调研

> 工单：`ai4-glmy`。研究范围为仓库内 `drafts/osp` 所含的 fast-agent-mcp `0.10.46` 第一方源码与随附文档；结论适用于该快照版本，不代表上游后续版本。
>
> 本文不重复端侧运行时调研，专门回答平台是否应复用 fast-agent-mcp 的会话历史。

## 结论

平台可以**受控复用 fast-agent-mcp 的 Harness 会话历史**，但仅限于“一个受平台生成且校验过的会话键，对应一个 TaskNode（或明确的 Execution Record）中的单一对话分支”的场景；不应把默认的 MCP 传输会话、`shared` 实例范围或运行时自动压缩作为平台的跨任务上下文层。

推荐的首版边界如下：

1. 为每个需要连续推理的执行记录生成不可猜测、符合 Harness 标识规则的 `session_id`；用**自定义 FastMCP 工具**把它显式传给 `HarnessMCPAdapter.invoke_agent()`，并以平台记录保存该映射。
2. 使用 `connection` 范围、稳定且专属的 `home` 目录、`session_history: true`；短生命周期 Worker 重启后，以相同 `session_id` 和同一 `home` 恢复。不同 TaskNode、租户和交接循环不可复用同一键。
3. 平台仍负责所有跨会话选择、父子任务交接、访问授权、保留期、删除与完整审计索引；fast-agent 仅保存该执行记录内部的模型对话。
4. 对需要逐条、可预测且由平台完全审计的上下文，调用时设 `RequestParams(use_history=False)`，由平台显式提供经过选择的材料。关闭该开关会阻止本轮模型历史累积和自动压缩，但 Harness 的文件持久化调用仍可能保存模板/快照，因此不能把它当作“完全不落盘”的隐私开关。
5. 生产环境将 `compaction.auto` 默认关掉，或仅在已验证可接受“模型生成摘要替换早期提示词”时启用；原文虽会归档，后续模型使用的是摘要而非原文。

因此，答案是“**优先复用，但作为受平台控制的每执行记录私有会话**”，而不是自行重做同一会话的逐轮拼接；平台不能放弃外层上下文编排和审计责任。

## 第一方证据与实际行为

### `use_history` 的默认值、覆盖与关闭效果

- `RequestParams.use_history` 默认 `True`，`AgentConfig.use_history` 同样默认 `True`；创建 Agent 配置时，后者会写入默认请求参数。证据：`drafts/osp/src/fast_agent/llm/request_params.py:87-90`、`drafts/osp/src/fast_agent/agents/agent_types.py:109-150`。
- 关闭后，正常会话历史钩子直接返回，不创建该轮对话的历史保存；自动压缩钩子也直接返回。证据：`drafts/osp/src/fast_agent/hooks/session_history.py:65-90`、`drafts/osp/src/fast_agent/hooks/compaction.py:67-82`。
- 这不是总的存储禁令：Harness 每次 `send`、`generate`、`structured` 成功后都会调用其已配置 persistence 的 `save()`；文件持久化最终执行 `Session.save_history()`。因此，`use_history=False` 时运行时不追加本轮提示词/回答，但 Harness 仍可能写入当前 Agent 的模板历史、`session.json` 元数据或先前已有内容。证据：`drafts/osp/src/fast_agent/core/harness.py:110-167`、`drafts/osp/src/fast_agent/core/harness_persistence.py:57-73`。
- `session_history: false` 或 `--no-home` 才会使 `AgentHarness` 不配置文件持久化；这与 `use_history` 独立。证据：`drafts/osp/src/fast_agent/core/harness.py:489-494`。`save_trajectory` 与 `use_history=True` 不能同时配置。证据：`drafts/osp/src/fast_agent/agents/agent_types.py:137-145`。

### Harness 标识、隔离与持久化位置

- `HarnessSessions` 按规范化后的 ID 管理会话；`None` 变为 `default`，显式 ID 限 1–128 字符，只允许字母、数字、`_`、`-`，首尾必须是字母或数字。证据：`drafts/osp/src/fast_agent/core/harness.py:52-70`、`drafts/osp/src/fast_agent/core/harness.py:692-705`。
- 一个 Harness Session 绑定一个自有 `AgentInstance`。同一进程中相同 ID 返回同一会话/实例；不同 ID 建立各自实例，因而内存历史隔离。一个会话同时进行第二个操作会被拒绝，避免同一历史被并发交叉写入。证据：`drafts/osp/src/fast_agent/core/harness.py:52-82`、`drafts/osp/src/fast_agent/core/harness.py:266-325`。
- `FileHarnessSessionPersistence.create_or_load()` 使用给定 ID 调用 `SessionManager.create_session_with_id()`，再由 `SessionHydrator` 将保存的 Agent 历史载入新实例；其 metadata 保存 `harness_session_id`。证据：`drafts/osp/src/fast_agent/core/harness_persistence.py:30-58`。
- 默认目录是运行工作区下的 `.fast-agent/sessions/<session_id>/`（可经 `home` 覆盖）。`SessionManager` 的 `base_dir` 为解析后的 home sessions 目录；每个会话含 `session.json` 和按 Agent 名称保存的 `history_<agent>.json`，写入时以 `history_<agent>_previous.json` 轮换。证据：`drafts/osp/src/fast_agent/session/session_manager.py:735-760`、`drafts/osp/src/fast_agent/session/session_manager.py:350-450`；文档说明见 `drafts/osp/docs/docs/ref/config_file.md:152-156`。

### MCP 会话键与作用域

- `Mcp-Session-Id` 只是可选传输标识，不是平台的通用业务状态键。`connection` 范围优先使用自定义工具传入的显式 `session_id`，没有才回退至请求头；`request` 范围无论传入何键都会生成新的 `request-<uuid>` 临时 Harness 会话。证据：`drafts/osp/src/fast_agent/mcp/server/harness_adapter.py:215-260`，第一方用法说明见 `drafts/osp/docs/docs/mcp/harness-adapter.md:143-154`。
- `request` 范围的每次调用结束后可清理该临时会话；默认 MCP 服务在 `instance_scope=request` 时选择此范围并配置清理。因此它不能用于跨调用恢复。证据：`drafts/osp/src/fast_agent/mcp/server/harness_adapter.py:156-189`、`drafts/osp/src/fast_agent/mcp/server/harness_app_server.py:159-195`。
- 托管的“每 Agent 一个 MCP 工具”接口不暴露通用 `session_id` 参数。需要 TaskNode/Execution Record 键时必须使用自定义 FastMCP 工具或 `harness_app.entrypoint`。证据：`drafts/osp/docs/docs/mcp/mcp-server.md:54-70`。
- `shared` 是默认实例范围，会重用单 Agent 给所有客户端；第一方文档仅建议在可信部署或刻意共享状态时使用。多租户、多个 TaskNode 的平台不得使用该默认值。证据：`drafts/osp/docs/docs/mcp/mcp-server.md:78-85`。

### 重启恢复、窗口与压缩

- 同一 `home` 持久卷上的 Worker 结束后，新 Worker 再以相同 `session_id` 创建 Harness Session，会按上述 hydration 路径恢复已保存的 Agent 历史；每次成功 Harness 调用在返回前保存，因此适合短生命周期 Worker 的“请求完成后重启”。证据：`drafts/osp/src/fast_agent/core/harness.py:110-150`、`drafts/osp/src/fast_agent/core/harness_persistence.py:30-73`。
- 恢复的前提是同一稳定 `home`、未被 `--no-home`/`session_history:false` 禁用、该 ID 未被并发 Worker 占有，并且新的 Worker 有能水合该会话所需的兼容 Agent 定义、模型/Provider 配置。会话文件锁会获取 owner；活跃会话由另一进程占有时不能安全并发恢复。证据：`drafts/osp/src/fast_agent/session/session_manager.py:818-876`、`drafts/osp/docs/docs/ref/go_command.md:68-70`。
- `session_history_window` 默认 20，限制的是保留的**会话数量**，新会话创建时会清理较旧会话；它不是每次模型请求的消息窗口。证据：`drafts/osp/src/fast_agent/config.py:2452-2460`、`drafts/osp/docs/docs/ref/config_file.md:152-152`。
- 消息级上下文收缩由 `compaction` 控制：默认自动开启，阈值为模型默认或 0.85，默认保留最后 2 个完整轮次，策略 `auto` 会优先选择 Provider 原生压缩，否则使用 fast-agent 摘要。证据：`drafts/osp/src/fast_agent/config.py:539-582`。
- 自动压缩仅对启用 `use_history` 的完整轮次生效；压缩把早期历史替换成带元数据的 checkpoint，保留尾部轮次。压缩前完整历史会存为会话目录的 `compacted_*.json`，失败时不替换历史。证据：`drafts/osp/src/fast_agent/hooks/compaction.py:67-125`、`drafts/osp/src/fast_agent/history/compaction.py:497-570`、`drafts/osp/src/fast_agent/history/compaction.py:699-821`。

### 导出与审计

- 普通会话保存采用原子临时文件与 current/previous 轮换，并同步写 `session.json` 快照；它提供崩溃恢复友好性，但并非不可篡改审计日志。证据：`drafts/osp/src/fast_agent/session/session_manager.py:350-450`。
- `fast-agent export` 可以将持久会话按 Agent 导出为 Codex JSONL 或 ATIF v1.8 JSON，目标可为 ID、目录或 `session.json`；`git_aware:true` 会把仓库状态加入导出。证据：`drafts/osp/docs/docs/ref/export_command.md:15-45`、`drafts/osp/docs/docs/ref/export_command.md:100-129`。
- 压缩 checkpoint 的 metadata 记录归档文件名、SHA-256、压缩前后计数、阈值上下文和生成摘要的请求/响应，能把摘要链接回原文归档；但平台仍应在每次调用后将导出文件哈希、session ID、Agent 名和执行记录 ID 写入自身的不可变审计存储。证据：`drafts/osp/src/fast_agent/history/compaction.py:755-821`。

## 可复现验证

以下命令在 `drafts/osp` 目录执行，不调用外部模型，也不更改产品依赖或锁文件。

```bash
uv run --frozen pytest -q \
  tests/unit/fast_agent/core/test_harness.py \
  tests/unit/fast_agent/mcp/test_harness_app_server.py \
  tests/unit/fast_agent/hooks/test_session_history.py \
  tests/unit/fast_agent/hooks/test_compaction_hook.py \
  tests/unit/fast_agent/session/test_snapshot.py
```

本次输出：`98 passed in 3.82s`。它覆盖文件型 Harness persistence、水合恢复、同 ID 复用、并发同会话拒绝、MCP request 范围临时 ID/清理、`use_history=False` 跳过会话历史钩子、压缩开关与快照读写。

可仅收集关键的第一方用例名称：

```bash
uv run --frozen pytest --collect-only -q \
  tests/unit/fast_agent/core/test_harness.py \
  tests/unit/fast_agent/mcp/test_harness_app_server.py \
  | grep -E 'persistence|resumed|same_session|session_scope|request_scope|connection'
```

本次输出至少包括：

```text
test_file_harness_persistence_attaches_session_manager
test_harness_session_validates_after_file_persistence_hydration
test_same_session_reuses_object_and_instance
test_concurrent_same_session_operations_reject
test_harness_mcp_request_scope_aligns_open_and_request_session_ids
test_harness_mcp_runtime_request_scope_disposes_each_call
```

## 风险与控制措施

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 使用默认 `shared` 或依赖传输层 `Mcp-Session-Id` | 跨用户/TaskNode 串话，现代无会话客户端无法稳定恢复 | 禁用 `shared`；自定义工具强制平台显式传入唯一业务键。 |
| `request` 范围 | 每次是新临时会话，调用结束会清理，无法恢复 | 需要连续历史时使用 `connection`；无状态执行才用 `request`。 |
| Worker 的 home 为临时磁盘 | 重启后找不到会话 | 将专属 fast-agent home 挂载到持久卷；记录版本与 home 归属。 |
| 同一键并行调用或跨进程占有 | 操作拒绝、锁冲突或不应依赖的并发顺序 | 平台按执行记录串行化；需要并行分支时生成新键，并通过平台显式交接。 |
| 自动压缩模型生成摘要 | 早期原文不再进入后续请求，摘要可能遗漏/扭曲 | 默认 `compaction.auto:false`；若启用，保存原始归档、导出并标记压缩版本。 |
| 将 `use_history:false` 误认为完全无落盘 | 模板、快照或旧历史仍可能被 Harness 保存 | 需要零持久化时同时用 `session_history:false` 或 `--no-home`，并隔离/删除已有会话目录。 |
| 本地 JSON 历史可被主机修改 | 不能作为合规意义的不可篡改证据 | 导出后由平台写入带访问控制的审计库并保存哈希/签名；严格控制 home 文件权限与租户目录。 |

## 推荐集成边界

```text
平台 Execution Record
  ├─ 生成并保存 session_id、tenant/task/attempt/agent 映射
  ├─ 串行化同一 session_id 的调用
  ├─ 选择跨节点交接材料、权限和保留/删除策略
  ├─ 调用自定义 MCP 工具(session_id=平台键)
  │    └─ HarnessMCPAdapter(connection scope)
  │         └─ FileHarnessSessionPersistence(专属持久 home)
  └─ 导出/哈希/归档 trace 与 compaction 原文
```

- **可交给 fast-agent：** 同一执行记录内的消息历史、重启后的加载、水合、会话级互斥、历史压缩和可导出的执行轨迹。
- **必须留在平台：** 业务 ID 到会话键的授权映射、跨 TaskNode/Owner/上游交接循环的材料筛选、租户隔离、幂等与并发调度、删除保留政策、不可篡改审计及敏感信息脱敏。
- **显式上下文模式：** 面向一次性 Worker、需绝对确定输入或需要跨任务精选事实时，调用 `RequestParams(use_history=False)`；同时把 `session_history` 关闭或不用 Harness 文件 persistence，避免产生任何本地快照副作用。
