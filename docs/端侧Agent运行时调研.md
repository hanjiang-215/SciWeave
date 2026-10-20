# fast-agent-mcp 端侧 Task Agent 运行时调研

> 状态：调研结论，供 `ai4-ufqu`（Task Agent 运行时与套件接入方案）决策使用；不是已批准的产品规格，也不引入运行时依赖。
>
> 调研日期：2026-10-19
>
> 研究对象：`drafts/osp` 中的 `evalstate/fast-agent` 源码（提交 `5d6e5b69`）及其随源码提供的第一方文档。

## 结论

SciWeave 首版应将 `fast-agent-mcp` 作为**受外围 Worker 调用的 Task Agent 运行时**，而不是把它当作任务调度器、消息队列、审计存储或人机通信系统。

推荐形态：

```text
Task Owner 的 harness ──MCP(Streamable HTTP)──→ Gateway（常驻）──spawn──→ Worker ──→ fast-agent Harness API
上游交接收集器 ────────消息队列──────────────────┘
```

- TaskNode 模板映射为 fast-agent 的 Agent 定义：固定基础 instruction、指定模型、按任务授权 MCP server、工具过滤和受审查的 Skills/Hooks。
- Worker 在调用前完成消息收集、Dependency Edge 激活判断、版本检查、上下文拼装、运行超时和审计；fast-agent 只执行一个已激活的 Task Agent loop。
- Agent 只能使用只读 MCP 和提交 Buffer 的 MCP；通知由 Worker 在写入 Buffer 后发出，不能让 Agent 直接以邮件正文代替受控提交。
- Task Owner 通过 MCP 而不是 A2A 接入：Codex CLI、Cursor、Claude Code 对外扩展面只有 MCP，未内置 A2A 客户端。
- 首版不应以 A2A 承载平台内部队列。A2A 面向 Agent 间协作，可在后续用于把受控 Agent 能力暴露给外部 Agent；它不替代 TaskNode 依赖、Buffer 或审核治理。

## 第一方能力证据

### Agent 定义与最小权限

`@fast.agent` 可声明 instruction、模型、MCP server、MCP 工具/资源/prompt 过滤、`use_history`、人类输入与 request parameters。`AgentConfig` 也将这些字段保存在单个 Agent 定义中。

因此每个 TaskNode 不应让运行时任意连接 MCP，而应生成最小权限的 Agent profile，例如只连接 `mapping-read`、`wiki-read` 和 `buffer-submit`，并显式列出各 server 允许的工具。

### Harness API 适合队列 Worker

官方 Harness API 的定位是无 TUI、无协议服务器地嵌入 Python Web 服务、批处理 Worker 和适配器；调用方可以通过 `AppOpenRequest.session_id` 明确指定会话亲和性，再用 `AgentRequest` 发起单次 turn。它明确建议队列 job 的 session key 按隔离 job 或需要连续上下文的实体选择。

SciWeave Worker 应使用 Harness API，而不是模拟交互终端：

1. 收到并持久化队列事件；
2. 验证事件发送者、TaskNode、版本和激活条件；
3. 选择 TaskNode 模板和最小能力清单；
4. 为本次 loop 选择受平台控制的 session key；
5. 调用 `HarnessApp.open()` / `HarnessSession.invoke()`；
6. 将输出、工具轨迹、失败和使用的输入版本写入 Execution Record；
7. 仅在成功建立 Buffer 后创建通知事件和邮件提醒。

### 历史机制：可选，不应替代平台事实

fast-agent 的 `use_history` 默认启用；会话历史可以持久化并在后续 session 中恢复。它还会压缩历史：保留模板与近期 turns，将较早 turns 摘要化，持久化时归档原历史。

因此不应再假设 fast-agent 没有上下文管理。`ai4-glmy` 将进一步验证受控 Session 模式是否适合 SciWeave。决策前保持两个候选：

- **显式上下文模式**：每个 Worker loop 使用 `use_history=False`，由 SciWeave 拼装 TaskNode 模板、已激活的上游交接、Owner 消息与前一轮输出引用；
- **受控 Session 模式**：开启历史，但 session key、保存目录、恢复、窗口和 compaction 由 Worker 显式控制，且每个 TaskNode/Execution Record/消息通道隔离。

无论使用哪种模式，Research Mapping、Buffer、AuditEvent 和 Execution Record 都仍是 SciWeave 的权威事实；fast-agent session 只是运行时上下文或可导出的执行轨迹。

### Skills 与 Hooks 的安全边界

fast-agent 会从默认技能目录发现 `SKILL.md`；发现有效 Skill 后，Agent 会获得 shell access，并将 Skill 描述加入系统提示词。故不能将开发仓库中默认发现的 Skills 直接挂给生产 Task Agent。

首版应对每个 TaskNode 模板显式声明可信 Skill 清单；无必要时禁用 Skills 与 shell。Hooks 仅用于 Worker 进程内的启动、提交前校验、执行后记录等受控行为，不能把 Task Owner 的个人 Codex Hook 当作服务器端 Agent Hook。

### A2A 的位置

源码例子表明 A2A 适配器可把 A2A `context_id` 映射到 `AgentRequest.session_id`，并把运行结果回传为协议 artifact。它适合后续给外部 Personal Agent 提供受治理的协议入口。

首版内部不采用 A2A，Owner 也不采用：主流 harness（Codex CLI、Cursor、Claude Code）没有内置 A2A 客户端，只有 MCP。Owner 侧改用 MCP（Streamable HTTP），Gateway 作为 MCP server；平台消息队列仍负责上游收集、重复投递、激活条件与审计。

## 建议的 TaskNode Agent Profile

```python
@fast.agent(
    name="task_<task_node_id>",
    instruction=resolved_tasknode_template,
    model=approved_model,
    servers=["mapping_read", "wiki_read", "buffer_submit"],
    tools={
        "mapping_read": ["get_formal_task_context"],
        "wiki_read": ["get_formal_evidence"],
        "buffer_submit": ["create_execution_submission"],
    },
    resources={},
    prompts={},
    skills=approved_skill_manifests,
    use_history=chosen_history_mode,
    human_input=False,
    shell=False,
)
```

这是目标设计轮廓，不是可直接运行的代码：真实 MCP 名称、工具名、模型、Skill 清单和 `use_history` 取值均尚未决策。

## 与当前通信模型的对应关系

| SciWeave 概念 | fast-agent 对应责任 | 责任边界 |
| --- | --- | --- |
| 上游 TaskNode 交接 | Worker 在调用前收集与验证 | 不交给 Agent 自行等待或聚合 |
| Task Owner 消息 | 经 Gateway MCP 工具进入 Worker 下一 loop 的请求 | 不与上游交接隐式混合 |
| 执行 loop | 一次 Harness 调用或受控 session turn | 输出必须回写 Execution Record |
| 结果审核 | Buffer + Owner 的 harness 经 MCP 调用 | 不由 Agent 自行接受 |
| 通知提醒 | Worker 的通知适配器 | 不作为审核或领域事实来源 |
| 跨 Agent 协议 | 后续可选 A2A adapter | 不替代内部队列与治理 |

## 后续验证

- `ai4-glmy`：验证 history、session 隔离、恢复和 compaction；
- `ai4-wd5l`：在运行时决策后确定 Agent 与 TaskNode Owner 的审核/返修流程；
- `ai4-csyj`：确定沿 Dependency Edge 发布 TaskNode 交接消息的流程；
- `ai4-v19u`：确定 MCP、Skills 和 Hooks 的平台提供能力及用户自带能力边界。

## 第一方来源

- fast-agent Harness API：`drafts/osp/docs/docs/agents/defining/harness-api.md`
- fast-agent Python API：`drafts/osp/docs/docs/agents/defining/python_api.md`
- fast-agent Agent Skills：`drafts/osp/docs/docs/guides/skills.md`
- fast-agent MCP client/server configuration：`drafts/osp/docs/docs/mcp/client-servers.md`
- fast-agent Compaction：`drafts/osp/docs/docs/guides/compaction.md`
- fast-agent AgentConfig 源码：`drafts/osp/src/fast_agent/agents/agent_types.py`
- fast-agent A2A adapter 示例：`drafts/osp/examples/a2a/agent_executor.py`
