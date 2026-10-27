# Workflow YAML 协议

> 本目录是工作流声明的唯一出处。`agent-definitions/workflows/` 只留指路说明，不要再往那里放副本。

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

## 合并规则：一个目录是一个命名空间

runtime 先合并目录中的 `*.yaml` 和 `*.yml`，再进行引用校验。**同一目录内 agent 名与工作流名必须全局唯一**——重名不是覆盖，是 `[duplicate_definition]`，整目录加载失败。

这就是本目录四个示例的 agent 名都带文件级前缀的原因：`router-writer` / `orchestrator-writer` / `parallel-writer` / `a2t-writer`。不加前缀时四份文件各定义一个 `writer`，目录加载必然失败。新增示例请沿用同样的前缀约定。

文件里只声明了一个 agent、没有 `workflows:` 段也是合法的（单 agent 预设），但有两条硬要求：

- 必须写在 `agents:` 段下面。扁平的单 agent 文件（`name:` 在顶层）会被解析成「零个定义」，runtime 报 `[no_definitions]` 而不是静默返回空配置；
- `version` 必须写。

## 字段校验：写错的键不再被静默丢弃

`load_config` 对顶层、`agents.<name>`、`workflows.<name>` 三处做键白名单校验，多出来的键报 `[unknown_field]`，并在错误里列出键名。合法键以 `AgentDefinition` / `WorkflowDefinition` 的字段为准，另加两个别名（`allowed_domain_mcps` 等同 `allowed_mcp_resources`，`children` 等同 `tools`）。

历史行为是逐字段取值、多出来的键直接消失，于是「照文档写了参数、配置能加载、参数从没生效」这种情况没有任何提示。现在它会直接失败。

## `version` 只在文件/目录加载路径上被强制

| 入口 | `version` 校验 |
| --- | --- |
| `load_workflow_yaml(file \| dir)`、`load_workflow_libs()` | **强制**，非 `1.x` 报 `[unsupported_config_version]` |
| `load_config(mapping)` | **不校验**，它是纯 mapping 校验层，不关心文档版本 |

所以补 `version: 1.0.0` 只对走文件/目录加载的路径有意义；直接构造 mapping 调 `load_config` 的调用方（测试、未来装配代码）拿着 `2.0.0` 也能过。

## 加载路径：标准目录 + 本地覆盖

`load_workflow_libs()` 与 `load_agent_registry()` / `load_mcp_registry()` 同构：

| 变量 | 作用 |
| --- | --- |
| `WORKFLOW_LIBS_PATH` | 出厂标准目录（本目录） |
| `LOCAL_WORKFLOW_LIBS_PATH` | 研究员自己的目录，同名定义覆盖标准目录 |

本地目录不存在是正常情况（多数研究员没有），此时只加载标准目录；标准目录不存在才报错。显式传参（`standard_path=` / `local_path=`）优先于环境变量。

## 其它约束

`type` 必须是 `Router`、`Orchestrator`、`Parallel` 或 `Agents as Tools`。`entry_agent`、`sub_agents`、`summarizer` 和 `final_writer` 都必须引用已声明 Agent；`final_writer` 是唯一允许执行最终写入的角色。Agent 的 `tools` 字段可声明 Agents as Tools 子 Agent，引用图不能形成循环。

配置文件只描述工作流，不执行 Python 代码；模型、地址和凭据通过环境变量提供。
