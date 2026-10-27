# Agent definitions

本目录存放可复制的 Agent 定义，结构约束见 [`../schema.yaml`](../schema.yaml)。

工作流声明不在这里，统一放在 [`../../libs/workflow-libs/`](../../libs/workflow-libs/)；`../workflows/` 只留指路说明。

`agents/` 下四个文件都是单 agent 定义，因此每个都必须写在 `agents:` 段下面：

```yaml
agents:
  biology-collaborator:
    name: biology-collaborator
    identity: 生物信息协作者
    instruction: |
      ...
    model: configure-in-your-own-environment
    allowed_mcp_resources: [research-mapping, sciencepal, draft-buffer]
    resources: []
```

漏掉 `agents:` 包裹（把 `name:` 写在顶层）会解析成零个定义，runtime 报 `[no_definitions]`。这条以前是静默返回空配置、退出码 0，研究员照 README 做出来的东西是空的还看不出来。

复制文件改 Agent 时，同时改 `agents:` 下的键名与文件里的 `name`，两者保持一致。
