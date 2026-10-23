# Workflow YAML 协议

工作流文件使用 YAML 1.2 数据模型，由 `runtime.load_workflow_yaml()` 读取。`version` 当前支持 `1.x`；工作流名称在同一目录内必须唯一。

```yaml
version: 1.0.0
name: literature-workflows
agents:
  researcher:
    identity: literature researcher
    instruction: Search and verify evidence.
    model: configured-by-environment
    allowed_mcp_resources: [research-wiki]
    resources: []
  writer:
    identity: final writer
    instruction: Write one draft.
    model: configured-by-environment
    allowed_mcp_resources: [draft-buffer]
    resources: []
workflows:
  literature-review:
    type: Orchestrator
    entry_agent: researcher
    sub_agents: [researcher]
    summarizer: researcher
    final_writer: writer
```

`type` 必须是 `Router`、`Orchestrator`、`Parallel` 或 `Agents as Tools`。`entry_agent`、`sub_agents`、`summarizer` 和 `final_writer` 都必须引用已声明 Agent；`final_writer` 是唯一允许执行最终写入的角色。Agent 的 `tools` 字段可声明 Agents as Tools 子 Agent，引用图不能形成循环。

runtime 先合并目录中的 `*.yaml` 和 `*.yml`，再进行引用校验。配置文件只描述工作流，不执行 Python 代码；模型、地址和凭据通过环境变量提供。
